"""Handler for get sync status query.

Composes API response from:
- sync_status: command-log fields (status, error, last_sync_at, consecutive_empty_fetches)
- bars: data-truth fields (bar_count, last_bar_at, is_stuck)

This decouples cascade-derived bar freshness from sync_status (which only
updates on SyncSymbolCommand). Eliminates false STUCK badges for cascade tfs.
``symbol`` is composite ``{code}:{exchange}`` throughout.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from pocketquant.api.market_data.handlers.status.dto import SyncStatusResult
from pocketquant.api.market_data.handlers.status.get_sync_status.query import GetSyncStatusQuery
from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.shared.value_objects import Interval
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.persistence.repositories.sync_status_repository import SyncStatusRepository

logger = get_logger(__name__)

# A sync is "stuck" if no new bar has appeared in 3× the interval cadence.
_STUCK_MULTIPLIER = 3


def _is_stuck(latest_bar_dt: datetime | None, interval: str) -> bool:
    if latest_bar_dt is None:
        return False
    cadence = INTERVAL_SECONDS.get(interval)
    if not cadence:
        return False
    age = (datetime.now(UTC) - latest_bar_dt).total_seconds()
    return age > _STUCK_MULTIPLIER * cadence


def _iso_z(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


async def _enrich_with_bars(
    symbol: str,
    interval_value: str,
    bar_repo: BarRepository,
) -> tuple[int, datetime | None]:
    """Return (bar_count, latest_bar_dt) read directly from bars collection."""
    interval = Interval(interval_value)
    latest = await bar_repo.get_latest(symbol, interval)
    count = await bar_repo.count(symbol, interval)
    return count, (latest.datetime if latest else None)


@handles(GetSyncStatusQuery)
class GetSyncStatusHandler(Handler[GetSyncStatusQuery, list[SyncStatusResult]]):
    """Handle getting all sync statuses, with bar-derived freshness."""

    def __init__(
        self,
        sync_status_repository: SyncStatusRepository,
        bar_repository: BarRepository,
    ):
        self._sync_status_repo = sync_status_repository
        self._bar_repo = bar_repository

    async def handle(self, request: GetSyncStatusQuery) -> list[SyncStatusResult]:
        statuses = await self._sync_status_repo.find_all()
        if not statuses:
            return []

        enrichments = await asyncio.gather(
            *(_enrich_with_bars(s.symbol, s.interval, self._bar_repo) for s in statuses),
            return_exceptions=True,
        )

        results: list[SyncStatusResult] = []
        for s, enrichment in zip(statuses, enrichments, strict=True):
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
                    is_stuck=_is_stuck(latest_dt, s.interval),
                )
            )
        return results
