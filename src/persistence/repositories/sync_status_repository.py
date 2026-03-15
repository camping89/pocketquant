"""Sync status repository for MongoDB persistence."""

from datetime import UTC, datetime

from src.common.constants import COLLECTION_SYNC_STATUS
from src.domain.ohlcv.entities import SyncStatus
from src.domain.shared.value_objects import Interval
from src.persistence.base_repository import BaseRepository


class SyncStatusRepository(BaseRepository):
    """Repository for sync status tracking."""

    _collection_name = COLLECTION_SYNC_STATUS

    async def upsert(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        status: str,
        bar_count: int | None = None,
        last_bar_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        """Upsert sync status for symbol/exchange/interval."""
        collection = self._collection()

        update_doc = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "interval": interval.value,
            "status": status,
            "last_sync_at": datetime.now(UTC),
            "bar_count": bar_count or 0,
            "last_bar_at": last_bar_at,
            "error_message": error_message,
        }

        await collection.update_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            },
            {"$set": update_doc},
            upsert=True,
        )

    async def find_all(self) -> list[SyncStatus]:
        """Get all sync statuses."""
        collection = self._collection()
        cursor = collection.find()
        return [SyncStatus.from_mongo(doc) async for doc in cursor]

    async def find_one(self, symbol: str, exchange: str, interval: Interval) -> SyncStatus | None:
        """Get sync status for specific symbol/exchange/interval."""
        collection = self._collection()

        doc = await collection.find_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            }
        )

        return SyncStatus.from_mongo(doc) if doc else None

    async def ensure_indexes(self) -> None:
        """Create compound index on (symbol, exchange, interval)."""
        collection = self._collection()
        await collection.create_index(
            [("symbol", 1), ("exchange", 1), ("interval", 1)],
            unique=True,
            name="ix_sync_status_symbol_exchange_interval",
        )
