"""BarAppService aggregates real-time ticks into bars at multiple intervals."""

import asyncio
import time
from collections import defaultdict
from typing import Any

from pocketquant.api.market_data.app_services.quote_dto import QuoteTick
from pocketquant.core.common.constants import CACHE_KEY_BAR_CURRENT
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.bar.services.bar_builder import BarBuilder, get_bar_start
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS, Interval
from pocketquant.infrastructure.persistence.redis import Cache
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)

# Minimum seconds between Redis flushes per (symbol, interval) key — throttle high-frequency ticks
BAR_CURRENT_FLUSH_MIN_INTERVAL_S = 0.2

# All 6 canonical timeframes tracked in-memory per symbol
_DEFAULT_INTERVALS = [
    Interval.MINUTE_1,
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]


def _ttl_for_interval(tf: Interval) -> int:
    """Return Redis TTL for a bar:current key. Longer TFs need longer TTLs.

    Formula: max(300, interval_seconds * 2) — ensures 1d bar survives 48h.
    """
    tf_seconds = INTERVAL_SECONDS.get(tf, 60)
    return max(300, tf_seconds * 2)


class BarAppService:
    """Aggregates real-time ticks into bars at multiple intervals.

    In-memory state: _bars[symbol_key][interval] = BarBuilder (running OHLCV).
    symbol_key is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    Cron sync_1m + cascade is the sole MongoDB writer — no upsert_bar here.
    On bar close: publish BarCompletedEvent (at-least-once) + force-flush Redis.
    BarRepository kept for get_current_bar DB fallback (SSE endpoint).
    """

    def __init__(
        self,
        cache: Cache,
        bar_repository: BarRepository,
        event_bus: EventBus,
        intervals: list[Interval] | None = None,
    ):
        self._cache = cache
        self._bar_repo = bar_repository  # kept for get_current_bar DB fallback
        self._event_bus = event_bus
        self._intervals = intervals or _DEFAULT_INTERVALS

        self._bars: dict[str, dict[Interval, BarBuilder]] = defaultdict(dict)
        self._last_flush_ts: dict[tuple[str, Interval], float] = {}

        self._lock = asyncio.Lock()

    async def add_tick(self, tick: QuoteTick) -> None:
        # tick.symbol is already composite ``{code}:{exchange}``
        symbol_key = tick.symbol.upper()

        async with self._lock:
            for interval in self._intervals:
                await self._process_tick_for_interval(tick, symbol_key, interval)

    async def _process_tick_for_interval(
        self,
        tick: QuoteTick,
        symbol_key: str,
        interval: Interval,
    ) -> None:
        current_bar = self._bars[symbol_key].get(interval)
        bar_start = get_bar_start(tick.timestamp, interval)

        if current_bar is None:
            current_bar = BarBuilder(
                symbol=symbol_key,
                interval=interval,
                bar_start=bar_start,
            )
            # Hydrate from Mongo when a bar already exists at this bucket
            # (e.g. after mid-bucket restart with cascade-populated in-progress
            # bar). Prevents the first post-restart tick price from overwriting
            # the true bucket-open and causing a visible chart gap.
            await self._seed_builder_from_mongo(current_bar)
            self._bars[symbol_key][interval] = current_bar

        elif current_bar.is_complete(tick.timestamp):
            completed = current_bar
            await self._save_completed_bar(completed)

            current_bar = BarBuilder(
                symbol=symbol_key,
                interval=interval,
                bar_start=bar_start,
            )
            self._bars[symbol_key][interval] = current_bar
            current_bar.add_tick(tick.price, tick.volume, tick.timestamp)
            await self._cache_current_bar(symbol_key, interval, current_bar, force=True)
            return

        current_bar.add_tick(tick.price, tick.volume, tick.timestamp)
        await self._cache_current_bar(symbol_key, interval, current_bar)

    async def _save_completed_bar(self, bar: BarBuilder) -> None:
        """Emit BarCompletedEvent and clean up Redis for the closed bar.

        NOTE: No MongoDB write here — cron sync_1m + cascade aggregator
        is the sole Mongo writer for `bars`. Removing upsert_bar is intentional.
        """
        if bar.is_empty():
            return

        if bar.open is None or bar.high is None or bar.low is None or bar.close is None:
            return

        # Emit event — at-least-once delivery; strategy subscribers must be idempotent
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
        )
        await self._event_bus.publish(event)

        # Delete the exact in-progress key for this (symbol, tf) so SSE stops
        # reporting a stale closed bar when no follow-up tick arrives (e.g. provider stall).
        exact_key = CACHE_KEY_BAR_CURRENT.format(
            symbol=bar.symbol.upper(),
            interval=bar.interval.value,
        )
        await self._cache.delete(exact_key)

        logger.info(
            "bar_completed_event_published",
            symbol=bar.symbol,
            interval=bar.interval.value,
            bar_start=bar.bar_start.isoformat(),
            tick_count=bar.tick_count,
        )

    async def _seed_builder_from_mongo(self, bar: BarBuilder) -> None:
        """Hydrate ``bar`` from Mongo if an aggregated bar exists at ``bar.bar_start``.

        Recovers the true bucket-open after a mid-bucket app restart where the
        BarBuilder would otherwise pick the first incoming tick price as the
        open. The Mongo source-of-truth is populated by the cascade aggregator.
        """
        try:
            existing = await self._bar_repo.get_latest(bar.symbol, bar.interval)
        except Exception as exc:
            logger.error("bar_app_service.seed_failed", error=str(exc))
            return

        if existing is None or existing.datetime != bar.bar_start:
            return

        bar.open = existing.open
        bar.high = existing.high
        bar.low = existing.low
        bar.close = existing.close
        bar.volume = existing.volume
        logger.info(
            "bar_app_service.seeded_from_mongo",
            symbol=bar.symbol,
            interval=bar.interval.value,
            bar_start=bar.bar_start.isoformat(),
            open=bar.open,
            close=bar.close,
        )

    async def _cache_current_bar(
        self,
        symbol_key: str,
        interval: Interval,
        bar: BarBuilder,
        force: bool = False,
    ) -> None:
        """Write bar:current Redis key, throttled per (symbol_key, interval).

        Throttle check is inside the caller's _lock to avoid races.
        force=True bypasses throttle (used on bar roll).
        """
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

    async def flush_all_bars(self) -> int:
        """Clear in-memory bars on shutdown. No Mongo write — cron handles persistence.

        Emits BarCompletedEvent for any non-empty in-progress bars so strategies
        see the partial close signal before process exits.
        """
        cleared_count = 0

        async with self._lock:
            for _symbol_key, intervals in self._bars.items():
                for _interval, bar in intervals.items():
                    if not bar.is_empty():
                        await self._save_completed_bar(bar)
                        cleared_count += 1

            self._bars.clear()
            self._last_flush_ts.clear()

        logger.info("bar_manager.bars_cleared", bars_cleared=cleared_count)
        return cleared_count

    @property
    def active_symbols(self) -> list[str]:
        return list(self._bars.keys())

    @property
    def intervals(self) -> list[Interval]:
        return self._intervals
