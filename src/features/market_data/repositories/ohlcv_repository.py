from datetime import UTC, datetime

from pymongo import UpdateOne
from pymongo.asynchronous.collection import AsyncCollection

from src.common.database import Database
from src.common.logging import get_logger
from src.features.market_data.models.ohlcv import (
    OHLCV,
    Interval,
    OHLCVCreate,
    SyncStatus,
)

logger = get_logger(__name__)


class OHLCVRepository:
    COLLECTION_NAME = "ohlcv"
    SYNC_STATUS_COLLECTION = "sync_status"

    @classmethod
    def _get_collection(cls) -> AsyncCollection:
        return Database.get_collection(cls.COLLECTION_NAME)

    @classmethod
    def _get_sync_collection(cls) -> AsyncCollection:
        return Database.get_collection(cls.SYNC_STATUS_COLLECTION)

    @classmethod
    async def upsert_many(cls, records: list[OHLCVCreate]) -> int:
        if not records:
            return 0

        collection = cls._get_collection()

        operations = []
        for record in records:
            ohlcv = OHLCV(**record.model_dump())
            doc = ohlcv.to_mongo()

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
        collection = cls._get_sync_collection()

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
        collection = cls._get_sync_collection()
        cursor = collection.find()

        statuses = []
        async for doc in cursor:
            statuses.append(SyncStatus.from_mongo(doc))

        return statuses
