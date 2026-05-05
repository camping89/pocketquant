"""Handler for get sync status query."""

from datetime import UTC, datetime

from pocketquant.api.market_data.handlers.status.dto import SyncStatusResult
from pocketquant.api.market_data.handlers.status.get_sync_status.query import GetSyncStatusQuery
from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.persistence.repositories.sync_status_repository import SyncStatusRepository

# A sync is "stuck" if no new bar has appeared in 3× the interval cadence.
_STUCK_MULTIPLIER = 3


def _is_stuck(last_bar_at, interval: str) -> bool:
    if last_bar_at is None:
        return False
    cadence = INTERVAL_SECONDS.get(interval)
    if not cadence:
        return False
    age = (datetime.now(UTC) - last_bar_at).total_seconds()
    return age > _STUCK_MULTIPLIER * cadence


@handles(GetSyncStatusQuery)
class GetSyncStatusHandler(Handler[GetSyncStatusQuery, list[SyncStatusResult]]):
    """Handle getting all sync statuses."""

    def __init__(self, sync_status_repository: SyncStatusRepository):
        self._sync_status_repo = sync_status_repository

    async def handle(self, request: GetSyncStatusQuery) -> list[SyncStatusResult]:
        statuses = await self._sync_status_repo.find_all()

        return [
            SyncStatusResult(
                symbol=s.symbol,
                exchange=s.exchange,
                interval=s.interval,
                status=s.status,
                bar_count=s.bar_count,
                last_sync_at=s.last_sync_at.isoformat().replace("+00:00", "Z") if s.last_sync_at else None,
                last_bar_at=s.last_bar_at.isoformat().replace("+00:00", "Z") if s.last_bar_at else None,
                error_message=s.error_message,
                consecutive_empty_fetches=s.consecutive_empty_fetches,
                is_stuck=_is_stuck(s.last_bar_at, s.interval),
            )
            for s in statuses
        ]
