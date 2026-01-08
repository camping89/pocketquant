"""Repository for OHLCV data persistence."""

from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import UpdateOne

from src.common.database import Database
from src.common.logging import get_logger
from src.features.market_data.models.ohlcv import (
    Interval,
    OHLCV,
    OHLCVCreate,
    SyncStatus,
)

logger = get_logger(__name__)


class OHLCVRepository:
    """Repository for OHLCV data operations."""

    COLLECTION_NAME = "ohlcv"
    SYNC_STATUS_COLLECTION = "sync_status"

    @classmethod
    def _get_collection(cls) -> AsyncIOMotorCollection:
        """Get the OHLCV collection."""
        return Database.get_collection(cls.COLLECTION_NAME)

    @classmethod
    def _get_sync_collection(cls) -> AsyncIOMotorCollection:
        """Get the sync status collection."""
        return Database.get_collection(cls.SYNC_STATUS_COLLECTION)

    @classmethod
    async def upsert_many(cls, records: list[OHLCVCreate]) -> int:
        """Upsert multiple OHLCV records.

        Uses bulk upsert to efficiently handle duplicates based on
        (symbol, exchange, interval, datetime) unique constraint.

        Args:
            records: List of OHLCV records to upsert.

        Returns:
            Number of records modified/inserted.
        """
        if not records:
            return 0

        collection = cls._get_collection()

        operations = []
        for record in records:
            ohlcv = OHLCV(**record.model_dump())
            doc = ohlcv.to_mongo()

            # Separate created_at for $setOnInsert to avoid conflict
            created_at = doc.pop("created_at", None)

            update_ops: dict = {"$set": doc}
            if created_at:
                update_ops["$setOnInsert"] = {"created_at": created_at}

            operations.append(
                UpdateOne(
                    {
                        "symbol": doc["symbol"],
                        "exchange": doc["exchange"],
                        "interval": doc["interval"],
                        "datetime": doc["datetime"],
                    },
                    update_ops,
                    upsert=True,
                )
            )

        result = await collection.bulk_write(operations, ordered=False)

        total = result.upserted_count + result.modified_count
        logger.info(
            "ohlcv_upserted",
            upserted=result.upserted_count,
            modified=result.modified_count,
            total=total,
        )

        return total

    @classmethod
    async def get_bars(
        cls,
        symbol: str,
        exchange: str,
        interval: Interval,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 1000,
    ) -> list[OHLCV]:
        """Get OHLCV bars for a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
            interval: Time interval.
            start_date: Optional start date filter.
            end_date: Optional end date filter.
            limit: Maximum number of bars to return.

        Returns:
            List of OHLCV records sorted by datetime descending.
        """
        collection = cls._get_collection()

        query: dict = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "interval": interval.value,
        }

        if start_date or end_date:
            query["datetime"] = {}
            if start_date:
                query["datetime"]["$gte"] = start_date
            if end_date:
                query["datetime"]["$lte"] = end_date

        cursor = collection.find(query).sort("datetime", -1).limit(limit)

        records = []
        async for doc in cursor:
            records.append(OHLCV.from_mongo(doc))

        return records

    @classmethod
    async def get_latest_bar(
        cls,
        symbol: str,
        exchange: str,
        interval: Interval,
    ) -> OHLCV | None:
        """Get the most recent bar for a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
            interval: Time interval.

        Returns:
            Most recent OHLCV record or None.
        """
        collection = cls._get_collection()

        doc = await collection.find_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            },
            sort=[("datetime", -1)],
        )

        if doc:
            return OHLCV.from_mongo(doc)
        return None

    @classmethod
    async def get_bar_count(
        cls,
        symbol: str,
        exchange: str,
        interval: Interval,
    ) -> int:
        """Get total bar count for a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
            interval: Time interval.

        Returns:
            Number of bars stored.
        """
        collection = cls._get_collection()

        return await collection.count_documents(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            }
        )

    @classmethod
    async def update_sync_status(
        cls,
        symbol: str,
        exchange: str,
        interval: Interval,
        status: str,
        bar_count: int | None = None,
        last_bar_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update sync status for a symbol/interval combination.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
            interval: Time interval.
            status: Sync status (pending, syncing, completed, error).
            bar_count: Optional total bar count.
            last_bar_at: Optional datetime of last bar.
            error_message: Optional error message if status is error.
        """
        collection = cls._get_sync_collection()

        update_doc: dict = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "interval": interval.value,
            "status": status,
            "last_sync_at": datetime.utcnow(),
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

        logger.info(
            "sync_status_updated",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
            status=status,
        )

    @classmethod
    async def get_sync_status(
        cls,
        symbol: str,
        exchange: str,
        interval: Interval,
    ) -> SyncStatus | None:
        """Get sync status for a symbol/interval combination.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
            interval: Time interval.

        Returns:
            SyncStatus if found, None otherwise.
        """
        collection = cls._get_sync_collection()

        doc = await collection.find_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            }
        )

        if doc:
            return SyncStatus.from_mongo(doc)
        return None

    @classmethod
    async def get_all_sync_statuses(cls) -> list[SyncStatus]:
        """Get all sync statuses.

        Returns:
            List of all sync statuses.
        """
        collection = cls._get_sync_collection()
        cursor = collection.find()

        statuses = []
        async for doc in cursor:
            statuses.append(SyncStatus.from_mongo(doc))

        return statuses
