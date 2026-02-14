"""Handler for get symbol sync status query."""

from src.common.constants import COLLECTION_SYNC_STATUS
from src.common.database import Database
from src.common.mediator import Handler, handles
from src.domain.shared.value_objects import Interval
from src.features.market_data.status.dto import SyncStatusResult
from src.features.market_data.status.get_symbol_sync_status.query import (
    GetSymbolSyncStatusQuery,
)
from src.infrastructure.persistence.schemas.ohlcv_schema import SyncStatus


@handles(GetSymbolSyncStatusQuery)
class GetSymbolSyncStatusHandler(
    Handler[GetSymbolSyncStatusQuery, SyncStatusResult]
):
    """Handle getting sync status for a specific symbol."""

    async def handle(self, request: GetSymbolSyncStatusQuery) -> SyncStatusResult:
        collection = Database.get_collection(COLLECTION_SYNC_STATUS)
        interval = Interval(request.interval)

        doc = await collection.find_one(
            {
                "symbol": request.symbol.upper(),
                "exchange": request.exchange.upper(),
                "interval": interval.value,
            }
        )

        if not doc:
            raise ValueError(
                f"No sync status found for {request.symbol}:{request.exchange}"
            )

        status = SyncStatus.from_mongo(doc)

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
