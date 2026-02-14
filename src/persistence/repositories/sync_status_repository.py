"""Sync status repository for MongoDB persistence."""

from datetime import UTC, datetime

from src.common.constants import COLLECTION_SYNC_STATUS
from src.domain.shared.value_objects import Interval
from src.persistence.base_repository import BaseRepository
from src.persistence.schemas.ohlcv_schema import SyncStatus


class SyncStatusRepository(BaseRepository):
    """Repository for sync status tracking."""

    _collection_name = COLLECTION_SYNC_STATUS

    @staticmethod
    async def upsert(
        symbol: str,
        exchange: str,
        interval: Interval,
        status: str,
        bar_count: int | None = None,
        last_bar_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        """Upsert sync status for symbol/exchange/interval."""
        collection = SyncStatusRepository._collection()

        update_doc: dict = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "interval": interval.value,
            "status": status,
            "last_sync_at": datetime.now(UTC),
        }

        if bar_count is not None:
            update_doc["bar_count"] = bar_count
        if last_bar_at is not None:
            update_doc["last_bar_at"] = last_bar_at
        if error_message is not None:
            update_doc["error_message"] = error_message

        await collection.update_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            },
            {"$set": update_doc},
            upsert=True,
        )

    @staticmethod
    async def find_all() -> list[SyncStatus]:
        """Get all sync statuses."""
        collection = SyncStatusRepository._collection()
        cursor = collection.find()
        return [SyncStatus.from_mongo(doc) async for doc in cursor]

    @staticmethod
    async def find_one(
        symbol: str, exchange: str, interval: Interval
    ) -> SyncStatus | None:
        """Get sync status for specific symbol/exchange/interval."""
        collection = SyncStatusRepository._collection()

        doc = await collection.find_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            }
        )

        return SyncStatus.from_mongo(doc) if doc else None

    @staticmethod
    async def ensure_indexes() -> None:
        """Create compound index on (symbol, exchange, interval)."""
        collection = SyncStatusRepository._collection()
        await collection.create_index(
            [
                ("symbol", 1),
                ("exchange", 1),
                ("interval", 1),
            ],
            unique=True,
        )
