"""Feed lag — how far a symbol's market data runs behind real time.

A delayed feed is not a broken one. The free TradingView plan serves CME bars
10-15 minutes late, and they keep arriving every minute, just behind the clock.
Lag is measured from the stored bars rather than from which provider serves the
symbol, so a new provider (delayed or real-time) needs no change here.

Only trading minutes count. A weekend, a holiday or the daily CME halt is the
market being shut, not the feed falling behind, so the lag reported on a Monday
open is the feed's delay rather than the length of the weekend.

The ``data_lag_check`` job writes one snapshot per tracked symbol to Redis each
minute; ``DataLagQueryService`` reads it back. A missing snapshot reads as
``unknown``, never as healthy.

``symbol`` is composite ``{code}:{exchange}`` throughout.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel

from pocketquant.core.common.constants import CACHE_KEY_DATA_LAG
from pocketquant.core.common.time import to_utc_iso
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.sync_status.entities import SyncStatus
from pocketquant.core.infra.persistence import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)

# Three 1m cadences. A real-time feed synced two seconds after each close sits
# at zero; anything past three minutes is a feed running behind the clock.
DELAYED_AFTER_SECONDS = 180
# Consecutive minute syncs that inserted nothing. A delayed feed still inserts a
# bar every minute, so a run of empty syncs while behind means the feed stopped
# (or a thin market went quiet), which is what separates stuck from delayed.
# Ten rather than three: YM trades thinly overnight and routinely skips a few
# minutes without anything being wrong.
STUCK_AFTER_EMPTY_SYNCS = 10
# Behind by more than this is stuck whatever the streak says. It catches a sync
# that stopped running altogether (the streak only grows when a sync runs), and
# it is twice the worst delay a delayed provider has shown (~15 min).
STUCK_AFTER_LAG_SECONDS = 30 * 60
# The 1m sync runs every minute while the market is open; a last run older than
# this means the job is not running, not that the feed is slow.
STUCK_AFTER_SYNC_AGE_SECONDS = 5 * 60
# How far back to count trading minutes. Enough to span a long weekend, and it
# bounds the work when a symbol has not received a bar in months.
_LAG_WINDOW = timedelta(days=4)
_ONE_MINUTE = timedelta(minutes=1)


class FeedState(StrEnum):
    OK = "ok"
    DELAYED = "delayed"
    STUCK = "stuck"
    CLOSED = "closed"
    UNKNOWN = "unknown"


def trading_seconds_behind(
    since: datetime,
    calendar: ITradingCalendarPort,
    now: datetime,
    *,
    window: timedelta = _LAG_WINDOW,
) -> int:
    """Trading seconds from ``since`` to ``now``.

    Minutes the calendar marks closed contribute nothing, so an overnight or
    weekend gap is not counted as falling behind. ``window`` caps how far back
    the count reaches.
    """
    start = max(since, now - window)
    if start >= now:
        return 0
    return 60 * len(calendar.trading_minutes(start, now))


def feed_lag_seconds(
    latest_1m_start: datetime | None, calendar: ITradingCalendarPort, now: datetime
) -> int | None:
    """How many trading seconds of closed 1m bars have not arrived yet.

    Counts from the close of the newest stored 1m bar. ``None`` when the symbol
    has no 1m bar at all.
    """
    if latest_1m_start is None:
        return None
    return trading_seconds_behind(latest_1m_start + _ONE_MINUTE, calendar, now)


def classify_feed(
    lag_seconds: int | None,
    empty_syncs: int,
    market_open: bool,
    sync_age_seconds: float | None = None,
) -> FeedState:
    """The feed's state from its lag and the health of the 1m sync.

    A shut market is ``closed`` whatever its lag. The sync stops shortly after
    the close, so a delayed feed's last minutes arrive only at the next open and
    the lag freezes at the delay; that is not something to flag all weekend.
    """
    if not market_open:
        return FeedState.CLOSED
    if lag_seconds is None:
        return FeedState.UNKNOWN
    if lag_seconds <= DELAYED_AFTER_SECONDS:
        return FeedState.OK
    stalled = (
        empty_syncs >= STUCK_AFTER_EMPTY_SYNCS
        or lag_seconds > STUCK_AFTER_LAG_SECONDS
        or (sync_age_seconds is not None and sync_age_seconds > STUCK_AFTER_SYNC_AGE_SECONDS)
    )
    return FeedState.STUCK if stalled else FeedState.DELAYED


def classify_sync_status(
    lag_seconds: int | None,
    status_1m: SyncStatus | None,
    market_open: bool,
    now: datetime,
) -> FeedState:
    """``classify_feed`` fed from the symbol's 1m sync-status row, if it has one."""
    if status_1m is None:
        return classify_feed(lag_seconds, 0, market_open)
    last_sync = status_1m.last_sync_at
    sync_age = (now - last_sync).total_seconds() if last_sync else None
    return classify_feed(lag_seconds, status_1m.consecutive_empty_fetches, market_open, sync_age)


@dataclass(frozen=True)
class DataLagSnapshot:
    symbol: str
    state: FeedState
    lag_seconds: int | None
    is_market_open: bool
    last_bar_at: str | None
    checked_at: str

    def to_cache_dict(self) -> dict:
        return {**asdict(self), "state": self.state.value}


async def compute_data_lag(
    symbol: str,
    bar_repo: BarRepository,
    sync_status_repo: SyncStatusRepository,
    calendar: ITradingCalendarPort,
    now: datetime | None = None,
) -> DataLagSnapshot:
    """Measure one symbol's feed lag from its newest 1m bar."""
    now = now or datetime.now(UTC)
    sym = symbol.upper()
    latest = await bar_repo.get_latest(sym, Interval.MINUTE_1)
    status = await sync_status_repo.find_one(sym, Interval.MINUTE_1)
    latest_dt = latest.datetime if latest else None
    lag = feed_lag_seconds(latest_dt, calendar, now)
    market_open = calendar.is_open(now)
    return DataLagSnapshot(
        symbol=sym,
        state=classify_sync_status(lag, status, market_open, now),
        lag_seconds=lag,
        is_market_open=market_open,
        last_bar_at=to_utc_iso(latest_dt),
        checked_at=to_utc_iso(now) or "",
    )


class GetDataLagQuery(BaseModel):
    symbol: str


class DataLagResponse(BaseModel):
    """``state`` is one of ``FeedState``; ``unknown`` when no check has run."""

    symbol: str
    state: FeedState
    lag_seconds: int | None = None
    is_market_open: bool | None = None
    last_bar_at: str | None = None
    checked_at: str | None = None


class DataLagQueryService:
    """Reads the snapshot the ``data_lag_check`` job last wrote."""

    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    async def get_data_lag(self, request: GetDataLagQuery) -> DataLagResponse:
        sym = request.symbol.upper()
        data = await self._cache.get(CACHE_KEY_DATA_LAG.format(symbol=sym))
        if not data:
            return DataLagResponse(symbol=sym, state=FeedState.UNKNOWN)
        return DataLagResponse(**data)
