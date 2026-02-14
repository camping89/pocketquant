"""Handler for get sync status query."""

from src.common.constants import COLLECTION_SYNC_STATUS
from src.common.database import Database
from src.common.mediator import Handler, handles
from src.features.market_data.status.dto import SyncStatusResult
from src.features.market_data.status.get_sync_status.query import GetSyncStatusQuery
from src.infrastructure.persistence.schemas.ohlcv_schema import SyncStatus


@handles(GetSyncStatusQuery)
class GetSyncStatusHandler(Handler[GetSyncStatusQuery, list[SyncStatusResult]]):
    """Handle getting all sync statuses."""

    async def handle(self, request: GetSyncStatusQuery) -> list[SyncStatusResult]:
        collection = Database.get_collection(COLLECTION_SYNC_STATUS)
        cursor = collection.find()

        statuses = [SyncStatus.from_mongo(doc) async for doc in cursor]

        return [
            SyncStatusResult(
                symbol=s.symbol,
                exchange=s.exchange,
                interval=s.interval,
                status=s.status,
                bar_count=s.bar_count,
                last_sync_at=s.last_sync_at.isoformat() if s.last_sync_at else None,
                last_bar_at=s.last_bar_at.isoformat() if s.last_bar_at else None,
                error_message=s.error_message,
            )
            for s in statuses
        ]
