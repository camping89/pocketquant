"""Handler for get symbol sync status query.

Composes API response from sync_status (status/error/last_sync_at) +
bars (count/last_bar_at/is_stuck), same pattern as GetSyncStatusHandler.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.execution.market_data.handlers.status.dto import SyncStatusResult
from pocketquant.execution.market_data.handlers.status.get_symbol_sync_status.query import (
    GetSymbolSyncStatusQuery,
)
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository
from pocketquant.infrastructure.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)

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


@handles(GetSymbolSyncStatusQuery)
class GetSymbolSyncStatusHandler(Handler[GetSymbolSyncStatusQuery, SyncStatusResult]):
    """Handle getting sync status for a specific composite symbol."""

    def __init__(
        self,
        sync_status_repository: SyncStatusRepository,
        bar_repository: BarRepository,
    ):
        self._sync_status_repo = sync_status_repository
        self._bar_repo = bar_repository

    async def handle(self, request: GetSymbolSyncStatusQuery) -> SyncStatusResult:
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
