import asyncio
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from pocketquant.core.common.constants import CACHE_KEY_BAR_CURRENT
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.bar.services.bar_builder_domain_service import (
    BarBuilderDomainService,
)
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.market_data.app_services.quote_dto import QuoteTick

logger = get_logger(__name__)

# Minimum seconds between Redis flushes per (symbol, interval) key — throttle high-frequency ticks
BAR_CURRENT_FLUSH_MIN_INTERVAL_S = 0.2
# A bar closes on the timer this long after its end; the timer runs every _TIMER_TICK_S.
_TIMER_CLOSE_GRACE_S = 0.5
_TIMER_TICK_S = 0.25
# Only bars up to 1h are cut at the session close.
_SESSION_CUT_MAX_INTERVAL_S = 3600
# More trading seconds than this without a tick (or uncovered at the bucket start) is a gap.
_GAP_AFTER_S = 60.0
_MINUTE = timedelta(minutes=1)

# All canonical timeframes tracked in-memory per symbol
_DEFAULT_INTERVALS = [
    Interval.MINUTE_1,
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
    Interval.WEEK_1,
]


def _trading_seconds(calendar: ITradingCalendarPort, a: datetime, b: datetime) -> float:
    """The part of ``[a, b)`` inside trading minutes; the wall gap when it is 60 s or less."""
    wall = (b - a).total_seconds()
    if wall <= _GAP_AFTER_S:
        return wall
    # trading_minutes steps from its start, so both bounds are minute-aligned.
    start = a.replace(second=0, microsecond=0)
    end = b.replace(second=0, microsecond=0)
    if end < b:
        end += _MINUTE
    return sum(
        (min(m + _MINUTE, b) - max(m, a)).total_seconds()
        for m in calendar.trading_minutes(start, end)
    )


def _ttl_for_interval(tf: Interval) -> int:
    """Return Redis TTL for a bar:current key. Longer TFs need longer TTLs.

    Formula: max(300, interval_seconds * 2) — ensures 1d bar survives 48h.
    """
    tf_seconds = INTERVAL_SECONDS.get(tf, 60)
    return max(300, tf_seconds * 2)


class BarAppService:
    """Aggregates real-time ticks into bars at multiple intervals.

    In-memory state: _bars[symbol_key][interval] = BarBuilderDomainService (running OHLCV).
    symbol_key is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    Cron sync_1m + cascade is the sole MongoDB writer — no upsert_bar here.
    On bar close: publish ``BarCompletedEvent`` after the bar lock is released, at most
    once. A restart or a feed gap loses a bar or sets ``gap``; consumers skip entries on
    gapped bars.
    BarRepository kept for get_current_bar DB fallback (SSE endpoint).
    """

    def __init__(
        self,
        cache: Cache,
        bar_repository: BarRepository,
        event_bus: EventBus,
        intervals: list[Interval] | None = None,
        calendar_factory: TradingCalendarFactory | None = None,
    ):
        self._cache = cache
        # Bucket boundaries belong to the symbol's calendar: an Exness weekly bar
        # opens on Sunday 00:00 UTC, not on Monday. Without a factory every symbol
        # uses the 24/7 grid, which is exactly right for crypto.
        self._calendar_factory = calendar_factory
        self._default_calendar = Continuous24x7Calendar()
        self._bar_repo = bar_repository  # kept for get_current_bar DB fallback
        self._event_bus = event_bus
        self._intervals = intervals or _DEFAULT_INTERVALS

        self._bars: dict[str, dict[Interval, BarBuilderDomainService]] = defaultdict(dict)
        self._last_flush_ts: dict[tuple[str, Interval], float] = {}
        # The end of the last closed bar per (symbol, interval), for the process lifetime.
        self._last_end: dict[tuple[str, Interval], datetime] = {}
        self._publishes_running = 0
        # Only the trading process writes or deletes ``bar:current``; a standby trader only
        # reads it as its seed. True until roles exist.
        self.publishes_current: bool = True
        # The latest 1m boundary whose bars are all closed and whose publish returned; a
        # draining trader releases only after it.
        self.last_closed_boundary: datetime | None = None
        self._calendars: dict[str, ITradingCalendarPort] = {}

        self._lock = asyncio.Lock()

    async def add_tick(self, tick: QuoteTick) -> None:
        # tick.symbol is already composite ``{code}:{exchange}``
        symbol_key = tick.symbol.upper()

        calendar = (
            await self._calendar_factory.for_symbol(symbol_key)
            if self._calendar_factory
            else self._default_calendar
        )
        self._calendars[symbol_key] = calendar
        events: list[BarCompletedEvent] = []
        async with self._lock:
            for interval in self._intervals:
                event = await self._process_tick_for_interval(tick, symbol_key, interval, calendar)
                if event is not None:
                    events.append(event)
            if events:
                # Counted under the lock, so a timer pass never sees 0 while this publish waits.
                self._publishes_running += 1
        if events:
            await self._publish(events)

    async def _publish(self, events: list[BarCompletedEvent]) -> None:
        """Publish closed bars in order, outside the bar lock; the caller counted this publish."""
        try:
            for event in events:
                await self._event_bus.publish(event)
                logger.debug(
                    "bar_completed_event_published",
                    symbol=event.symbol,
                    interval=event.interval,
                    bar_start=event.bar_start.isoformat() if event.bar_start else None,
                    tick_count=event.tick_count,
                )
        finally:
            self._publishes_running -= 1

    async def _process_tick_for_interval(
        self,
        tick: QuoteTick,
        symbol_key: str,
        interval: Interval,
        calendar: ITradingCalendarPort | None = None,
    ) -> BarCompletedEvent | None:
        """Add ``tick`` to its bar; return the event of the bar it closed, if any."""
        calendar = calendar or self._default_calendar
        current_bar = self._bars[symbol_key].get(interval)
        bar_start = calendar.bar_start(tick.timestamp, interval)

        if current_bar is None:
            last_end = self._last_end.get((symbol_key, interval))
            if last_end is not None and bar_start < last_end:
                logger.debug(
                    "bar.late_tick_dropped",
                    symbol=symbol_key,
                    interval=interval.value,
                    tick_ts=tick.timestamp.isoformat(),
                )
                return None
            current_bar = self._new_builder(symbol_key, interval, bar_start, calendar)
            if last_end is not None:
                # The previous bar of this key closed here, so coverage starts at the bucket.
                current_bar.last_tick_at = bar_start
                current_bar.coverage_start = bar_start
            else:
                await self._seed_from_redis(current_bar, calendar, tick.timestamp)
            assert current_bar.coverage_start is not None
            # One rule for every path: a seeded builder inherits the late start of the
            # process that wrote the seed.
            if _trading_seconds(calendar, bar_start, current_bar.coverage_start) > _GAP_AFTER_S:
                current_bar.gap = True
            self._bars[symbol_key][interval] = current_bar

        # A later bucket closes the current bar. On a uniform grid this is the
        # same test as ``tick >= bar_end``, but a session calendar's buckets are
        # not all one interval long (a DST day, a short last bar of the session).
        elif bar_start > current_bar.bar_start:
            event = await self._complete_bar(
                current_bar, calendar, closed_by="tick", closing_tick_at=tick.timestamp
            )

            current_bar = self._new_builder(symbol_key, interval, bar_start, calendar)
            current_bar.coverage_start = bar_start
            self._bars[symbol_key][interval] = current_bar
            current_bar.add_tick(tick.price, tick.volume, tick.timestamp)
            await self._cache_current_bar(symbol_key, interval, current_bar, force=True)
            return event

        last = current_bar.last_tick_at
        if last is not None and _trading_seconds(calendar, last, tick.timestamp) > _GAP_AFTER_S:
            current_bar.gap = True
        current_bar.add_tick(tick.price, tick.volume, tick.timestamp)
        await self._cache_current_bar(symbol_key, interval, current_bar)
        return None

    def _new_builder(
        self,
        symbol_key: str,
        interval: Interval,
        bar_start: datetime,
        calendar: ITradingCalendarPort,
    ) -> BarBuilderDomainService:
        """A builder for ``bar_start``; bars up to 1h end no later than the session close."""
        bar_end = None
        if INTERVAL_SECONDS[interval] <= _SESSION_CUT_MAX_INTERVAL_S:
            full_end = bar_start + timedelta(seconds=INTERVAL_SECONDS[interval])
            try:
                close = calendar.session_close(calendar.session_date(bar_start))
                bar_end = min(full_end, close + timedelta(seconds=1))
            except KeyError:
                bar_end = full_end
        return BarBuilderDomainService(
            symbol=symbol_key, interval=interval, bar_start=bar_start, bar_end=bar_end
        )

    async def close_due_bars(self) -> None:
        """Close every bar whose end is at least the grace in the past, then publish them."""
        now = get_current_time()
        grace = timedelta(seconds=_TIMER_CLOSE_GRACE_S)
        events: list[BarCompletedEvent] = []
        async with self._lock:
            for symbol_key, builders in self._bars.items():
                calendar = self._calendars.get(symbol_key, self._default_calendar)
                for interval, builder in list(builders.items()):
                    assert builder.bar_end is not None
                    if builder.bar_end + grace > now:
                        continue
                    event = await self._complete_bar(
                        builder, calendar, closed_by="timer", closing_tick_at=None
                    )
                    del builders[interval]
                    if event is not None:
                        events.append(event)
            if events:
                self._publishes_running += 1
        if events:
            await self._publish(events)
        # Every bar that ended at or before this boundary is closed, by a tick or by this
        # pass; a running publish holds it until a later pass.
        if self._publishes_running == 0:
            self.last_closed_boundary = (now - grace).replace(second=0, microsecond=0)

    async def run_close_timer(self) -> None:
        while True:
            await asyncio.sleep(_TIMER_TICK_S)
            try:
                await self.close_due_bars()
            except Exception:
                logger.error("bar.close_timer_failed", exc_info=True)

    async def _complete_bar(
        self,
        bar: BarBuilderDomainService,
        calendar: ITradingCalendarPort,
        *,
        closed_by: str,
        closing_tick_at: datetime | None,
    ) -> BarCompletedEvent | None:
        """Close ``bar`` under the bar lock and return its event; the caller publishes it.

        NOTE: No MongoDB write here — cron sync_1m + cascade aggregator
        is the sole Mongo writer for `bars`. Removing upsert_bar is intentional.
        """
        assert bar.bar_end is not None
        self._last_end[(bar.symbol, bar.interval)] = bar.bar_end
        if bar.is_empty():
            return None

        if bar.open is None or bar.high is None or bar.low is None or bar.close is None:
            return None

        if (
            bar.last_tick_at is not None
            and _trading_seconds(calendar, bar.last_tick_at, bar.bar_end) > _GAP_AFTER_S
        ):
            bar.gap = True
        # At most once: a bar is never re-published.
        # bar.symbol is composite ``{code}:{exchange}``
        event = BarCompletedEvent(
            symbol=bar.symbol,
            interval=bar.interval.value,
            bar_start=bar.bar_start,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            tick_count=bar.tick_count,
            bar_end=bar.bar_end,
            gap=bar.gap,
            closed_at=get_current_time(),
            closing_tick_at=closing_tick_at,
            closed_by=closed_by,
        )

        # Delete the exact in-progress key for this (symbol, tf) so SSE stops
        # reporting a stale closed bar when no follow-up tick arrives (e.g. provider stall).
        # The delete stays under the lock: the next builder writes the same key right after.
        if self.publishes_current:
            exact_key = CACHE_KEY_BAR_CURRENT.format(
                symbol=bar.symbol.upper(),
                interval=bar.interval.value,
            )
            await self._cache.delete(exact_key)
        return event

    async def _seed_from_redis(
        self, bar: BarBuilderDomainService, calendar: ITradingCalendarPort, first_tick: datetime
    ) -> None:
        """Restore ``bar`` from its ``bar:current`` key when that seed covers ``first_tick``.

        A covering seed has the same bucket, a ``coverage_start`` (older images write none)
        and a ``last_update`` at most 60 trading seconds before the first tick. Otherwise
        coverage starts at the first tick.
        """
        key = CACHE_KEY_BAR_CURRENT.format(symbol=bar.symbol, interval=bar.interval.value)
        try:
            seed = await self._cache.get(key)
        except Exception as exc:
            logger.error("bar_app_service.seed_failed", error=str(exc))
            seed = None
        updated = seed.get("last_update") if isinstance(seed, dict) else None
        if (
            not isinstance(seed, dict)
            or seed.get("bar_start") != bar.bar_start.isoformat()
            or not seed.get("coverage_start")
            or not isinstance(updated, int | float)
            or _trading_seconds(calendar, datetime.fromtimestamp(updated, UTC), first_tick)
            > _GAP_AFTER_S
        ):
            bar.coverage_start = first_tick
            return
        bar.open = seed["open"]
        bar.high = seed["high"]
        bar.low = seed["low"]
        bar.close = seed["close"]
        bar.volume = seed["volume"]
        bar.tick_count = seed["tick_count"]
        bar.gap = bool(seed.get("gap"))
        bar.coverage_start = datetime.fromisoformat(seed["coverage_start"])
        bar.last_tick_at = datetime.fromtimestamp(updated, UTC)
        logger.info(
            "bar_app_service.seeded_from_redis",
            symbol=bar.symbol,
            interval=bar.interval.value,
            bar_start=bar.bar_start.isoformat(),
        )

    async def _cache_current_bar(
        self,
        symbol_key: str,
        interval: Interval,
        bar: BarBuilderDomainService,
        force: bool = False,
    ) -> None:
        """Write bar:current Redis key, throttled per (symbol_key, interval).

        Throttle check is inside the caller's _lock to avoid races.
        force=True bypasses throttle (used on bar roll).
        """
        if not self.publishes_current:
            return
        now = time.monotonic()
        flush_key = (symbol_key, interval)

        if not force:
            last = self._last_flush_ts.get(flush_key, 0.0)
            if now - last < BAR_CURRENT_FLUSH_MIN_INTERVAL_S:
                return

        cache_key = CACHE_KEY_BAR_CURRENT.format(symbol=symbol_key, interval=interval.value)
        ttl = _ttl_for_interval(interval)
        # Inject wall-clock last_update (Unix seconds) for SSE staleness_ms calculation
        bar_dict = bar.to_dict()
        bar_dict["last_update"] = time.time()
        await self._cache.set(cache_key, bar_dict, ttl=ttl)
        self._last_flush_ts[flush_key] = now

    async def get_current_bar(
        self,
        symbol: str,
        interval: Interval,
    ) -> dict[str, Any] | None:
        """``symbol`` is composite ``{code}:{exchange}``."""
        cache_key = CACHE_KEY_BAR_CURRENT.format(symbol=symbol.upper(), interval=interval.value)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Fallback: no live feed — return latest bar from DB as current bar
        try:
            bar = await self._bar_repo.get_latest(symbol, interval)
        except Exception as exc:
            logger.error("bar_manager.get_latest_failed", error=str(exc))
            return None
        if bar is None:
            return None

        return {
            "symbol": bar.symbol,
            "interval": interval.value,
            "bar_start": bar.datetime.isoformat() if bar.datetime else None,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "tick_count": 0,
        }

    @property
    def active_symbols(self) -> list[str]:
        return list(self._bars.keys())

    @property
    def intervals(self) -> list[Interval]:
        return self._intervals
