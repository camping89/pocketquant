"""Handler for get symbol sync status query."""

from pocketquant.api.market_data.handlers.status.dto import SyncStatusResult
from pocketquant.api.market_data.handlers.status.get_symbol_sync_status.query import (
    GetSymbolSyncStatusQuery,
)
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.shared.value_objects import Interval
from pocketquant.core.persistence.repositories.sync_status_repository import SyncStatusRepository


@handles(GetSymbolSyncStatusQuery)
class GetSymbolSyncStatusHandler(Handler[GetSymbolSyncStatusQuery, SyncStatusResult]):
    """Handle getting sync status for a specific symbol."""

    def __init__(self, sync_status_repository: SyncStatusRepository):
        self._sync_status_repo = sync_status_repository

    async def handle(self, request: GetSymbolSyncStatusQuery) -> SyncStatusResult:
        interval = Interval(request.interval)

        status = await self._sync_status_repo.find_one(request.symbol, request.exchange, interval)

        if not status:
            raise NotFoundError(f"No sync status found for {request.symbol}:{request.exchange}")

        return SyncStatusResult(
            symbol=status.symbol,
            exchange=status.exchange,
            interval=status.interval,
            status=status.status,
            bar_count=status.bar_count,
            last_sync_at=status.last_sync_at.isoformat() if status.last_sync_at else None,
            last_bar_at=status.last_bar_at.isoformat() if status.last_bar_at else None,
            error_message=status.error_message,
        )
