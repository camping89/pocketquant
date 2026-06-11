"""Sync-status query service — bar-derived freshness composition.

Composes API response from:
- sync_status: command-log fields (status, error, last_sync_at, consecutive_empty_fetches)
- bars: data-truth fields (bar_count, last_bar_at, is_stuck)

Decouples cascade-derived bar freshness from sync_status (which only updates on
SyncSymbolCommand). Eliminates false STUCK badges for cascade timeframes.
``symbol`` is composite ``{code}:{exchange}`` throughout.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)

logger = get_logger(__name__)

# A sync is "stuck" if no new bar has appeared in 3× the interval cadence.
_STUCK_MULTIPLIER = 3


@dataclass
class GetSyncStatusQuery:
    """Query to get all sync statuses."""

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


class SyncStatusQueryService:
    """Query sync status for all symbols or a single symbol."""

    def __init__(
        self,
        sync_status_repository: SyncStatusRepository,
        bar_repository: BarRepository,
    ) -> None:
        self._sync_status_repo = sync_status_repository
        self._bar_repo = bar_repository

    async def get_sync_status(self, request: GetSyncStatusQuery) -> list[SyncStatusResult]:
        """Return all sync statuses with bar-derived freshness."""
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

    async def get_symbol_sync_status(self, request: GetSymbolSyncStatusQuery) -> SyncStatusResult:
        """Return sync status for a single composite symbol. 404 if not found."""
        interval = Interval(request.interval)

        status = await self._sync_status_repo.find_one(request.symbol, interval)
        if not status:
            raise NotFoundError(f"No sync status found for {request.symbol}")

        latest_bar = await self._bar_repo.get_latest(status.symbol, interval)
        bar_count = await self._bar_repo.count(status.symbol, interval)
        latest_dt = latest_bar.datetime if latest_bar else None

        return SyncStatusResult(
            symbol=status.symbol,
            interval=status.interval,
            status=status.status,
            bar_count=bar_count,
            last_sync_at=_iso_z(status.last_sync_at),
            last_bar_at=_iso_z(latest_dt),
            error_message=status.error_message,
            consecutive_empty_fetches=status.consecutive_empty_fetches,
            is_stuck=_is_stuck(latest_dt, status.interval),
        )
