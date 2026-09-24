"""Sync-status query service — bar-derived freshness composition.

Composes API response from:
- sync_status: command-log fields (status, error, last_sync_at, consecutive_empty_fetches)
- bars: data-truth fields (bar_count, last_bar_at, is_stuck)
- the symbol's 1m feed: lag_seconds / is_delayed (see ``data_lag_service``)

Decouples cascade-derived bar freshness from sync_status (which only updates on
SyncSymbolCommand). Eliminates false STUCK badges for cascade timeframes.
``symbol`` is composite ``{code}:{exchange}`` throughout.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import to_utc_iso
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.sync_status.entities import SyncStatus
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)
from pocketquant.engine.market_data.data_lag_service import (
    FeedState,
    classify_sync_status,
    feed_lag_seconds,
    trading_seconds_behind,
)

logger = get_logger(__name__)

# A sync is "stuck" if no new bar has appeared in 3× the interval cadence.
_STUCK_MULTIPLIER = 3
# A stuck feed is behind too; the flag says "late", the badge says why.
_BEHIND = frozenset({FeedState.DELAYED, FeedState.STUCK})


@dataclass
class GetSyncStatusQuery:
    pass


@dataclass
class GetSymbolSyncStatusQuery:
    """Query to get sync status for a specific composite symbol."""

    symbol: str
    interval: str = "1d"


@dataclass
class SyncStatusResult:
    """Result of a sync status query. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    interval: str
    status: str
    bar_count: int | None = None
    last_sync_at: str | None = None
    last_bar_at: str | None = None
    error_message: str | None = None
    # Diagnostics for UI: counter + derived stuck flag.
    consecutive_empty_fetches: int = 0
    is_stuck: bool = False
    is_market_open: bool = True
    # Per symbol, from its 1m feed, repeated on every interval row: a delayed
    # feed delays every timeframe cascaded from it by the same amount.
    lag_seconds: int | None = None
    is_delayed: bool = False


@dataclass(frozen=True)
class _Feed:
    lag_seconds: int | None
    state: FeedState


def _is_stuck(
    latest_bar_dt: datetime | None,
    interval: str,
    calendar: ITradingCalendarPort,
    feed: _Feed,
    now: datetime,
) -> bool:
    """No new bar in 3x this interval's cadence beyond what the feed delay explains.

    The 1m row is the feed itself, so it is stuck exactly when the feed is: behind
    and no longer inserting bars. Every other row may be as late as a delayed
    feed plus three of its own cadences. A stuck feed earns no allowance, or a
    stalled feed would excuse every row built from it.
    """
    if interval == Interval.MINUTE_1.value:
        return feed.state is FeedState.STUCK
    if latest_bar_dt is None:
        return False
    cadence = INTERVAL_SECONDS.get(interval)
    if not cadence:
        return False
    allowance = (feed.lag_seconds or 0) if feed.state is FeedState.DELAYED else 0
    threshold = _STUCK_MULTIPLIER * cadence + allowance
    # Wall-clock age bounds trading age from above, so the common fresh case
    # skips the calendar walk. Past it, only trading minutes count: a weekend
    # is the market being shut, not the row falling behind.
    if (calendar.previous_close(now) - latest_bar_dt).total_seconds() <= threshold:
        return False
    window = timedelta(seconds=threshold) + timedelta(days=4)
    return trading_seconds_behind(latest_bar_dt, calendar, now, window=window) > threshold


def _iso_z(dt: datetime | None) -> str | None:
    return to_utc_iso(dt)


async def _enrich_with_bars(
    symbol: str,
    interval_value: str,
    bar_repo: BarRepository,
) -> tuple[int, datetime | None]:
    interval = Interval(interval_value)
    latest = await bar_repo.get_latest(symbol, interval)
    count = await bar_repo.count(symbol, interval)
    return count, (latest.datetime if latest else None)


class SyncStatusQueryService:
    def __init__(
        self,
        sync_status_repository: SyncStatusRepository,
        bar_repository: BarRepository,
        calendar_factory: TradingCalendarFactory,
    ) -> None:
        self._sync_status_repo = sync_status_repository
        self._bar_repo = bar_repository
        self._calendar_factory = calendar_factory

    async def get_sync_status(self, request: GetSyncStatusQuery) -> list[SyncStatusResult]:
        statuses = await self._sync_status_repo.find_all()
        if not statuses:
            return []

        # One round of concurrency for both lookups, not two.
        enrichments, calendars = await asyncio.gather(
            asyncio.gather(
                *(_enrich_with_bars(s.symbol, s.interval, self._bar_repo) for s in statuses),
                return_exceptions=True,
            ),
            asyncio.gather(
                *(self._calendar_factory.for_symbol(s.symbol) for s in statuses),
            ),
        )

        now = datetime.now(UTC)
        calendar_of = {s.symbol: cal for s, cal in zip(statuses, calendars, strict=True)}
        status_1m = {s.symbol: s for s in statuses if s.interval == Interval.MINUTE_1.value}
        feeds = await self._feeds(calendar_of, status_1m, now)

        results: list[SyncStatusResult] = []
        for s, enrichment, calendar in zip(statuses, enrichments, calendars, strict=True):
            if isinstance(enrichment, BaseException):
                logger.warning(
                    "sync_status.enrich_failed",
                    symbol=s.symbol,
                    interval=s.interval,
                    error=str(enrichment),
                )
                bar_count = s.bar_count
                latest_dt = s.last_bar_at
            else:
                bar_count, latest_dt = enrichment

            results.append(
                SyncStatusResult(
                    symbol=s.symbol,
                    interval=s.interval,
                    status=s.status,
                    bar_count=bar_count,
                    last_sync_at=_iso_z(s.last_sync_at),
                    last_bar_at=_iso_z(latest_dt),
                    error_message=s.error_message,
                    consecutive_empty_fetches=s.consecutive_empty_fetches,
                    is_stuck=_is_stuck(latest_dt, s.interval, calendar, feeds[s.symbol], now),
                    is_market_open=calendar.is_open(now),
                    lag_seconds=feeds[s.symbol].lag_seconds,
                    is_delayed=feeds[s.symbol].state in _BEHIND,
                )
            )
        return results

    async def _feeds(
        self,
        calendar_of: dict[str, ITradingCalendarPort],
        status_1m: dict[str, SyncStatus],
        now: datetime,
    ) -> dict[str, _Feed]:
        """One 1m-feed reading per symbol, shared by all of its interval rows."""
        symbols = list(calendar_of)
        latest = await asyncio.gather(
            *(self._bar_repo.get_latest(sym, Interval.MINUTE_1) for sym in symbols),
            return_exceptions=True,
        )
        feeds: dict[str, _Feed] = {}
        for sym, bar in zip(symbols, latest, strict=True):
            if isinstance(bar, BaseException):
                logger.warning("sync_status.feed_lag_failed", symbol=sym, error=str(bar))
                feeds[sym] = _Feed(None, FeedState.UNKNOWN)
                continue
            calendar = calendar_of[sym]
            lag = feed_lag_seconds(bar.datetime if bar else None, calendar, now)
            state = classify_sync_status(lag, status_1m.get(sym), calendar.is_open(now), now)
            feeds[sym] = _Feed(lag, state)
        return feeds

    async def get_symbol_sync_status(self, request: GetSymbolSyncStatusQuery) -> SyncStatusResult:
        """Return sync status for a single composite symbol. 404 if not found."""
        interval = Interval(request.interval)

        status = await self._sync_status_repo.find_one(request.symbol, interval)
        if not status:
            raise NotFoundError(f"No sync status found for {request.symbol}")

        latest_bar = await self._bar_repo.get_latest(status.symbol, interval)
        bar_count = await self._bar_repo.count(status.symbol, interval)
        latest_dt = latest_bar.datetime if latest_bar else None
        calendar = await self._calendar_factory.for_symbol(status.symbol)
        now = datetime.now(UTC)
        status_1m = (
            status
            if interval is Interval.MINUTE_1
            else await self._sync_status_repo.find_one(status.symbol, Interval.MINUTE_1)
        )
        by_symbol = {status.symbol: status_1m} if status_1m else {}
        feed = (await self._feeds({status.symbol: calendar}, by_symbol, now))[status.symbol]

        return SyncStatusResult(
            symbol=status.symbol,
            interval=status.interval,
            status=status.status,
            bar_count=bar_count,
            last_sync_at=_iso_z(status.last_sync_at),
            last_bar_at=_iso_z(latest_dt),
            error_message=status.error_message,
            consecutive_empty_fetches=status.consecutive_empty_fetches,
            is_stuck=_is_stuck(latest_dt, status.interval, calendar, feed, now),
            is_market_open=calendar.is_open(now),
            lag_seconds=feed.lag_seconds,
            is_delayed=feed.state in _BEHIND,
        )
