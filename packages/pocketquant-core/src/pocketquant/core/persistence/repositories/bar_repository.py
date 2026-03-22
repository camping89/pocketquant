"""Bar repository for MongoDB persistence."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from pocketquant.core.common.constants import COLLECTION_BARS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.value_objects import Interval
from pocketquant.core.persistence.base_repository import BaseRepository
from pymongo.errors import BulkWriteError

logger = get_logger(__name__)


class BarRepository(BaseRepository):
    """Repository for bar data operations."""

    _collection_name = COLLECTION_BARS

    async def insert_many(self, records: list[Bar]) -> int:
        """Bulk insert OHLCV bars, skipping duplicates. Returns count of newly inserted."""
        if not records:
            return 0

        collection = self._collection()
        now = datetime.now(UTC)
        docs = []
        for bar in records:
            doc = bar.to_mongo()
            doc["created_at"] = now
            doc["updated_at"] = now
            docs.append(doc)

        try:
            # ordered=False: continues past duplicate key errors,
            # inserts all non-duplicate docs, skips existing ones
            result = await collection.insert_many(docs, ordered=False)
            inserted = len(result.inserted_ids)
            logger.info(
                "data_sync.inserted",
                inserted_count=inserted,
                total_submitted=len(docs),
            )
            return inserted
        except BulkWriteError as e:
            # BulkWriteError is raised even for partial success with ordered=False.
            # nInserted tells us how many actually made it in.
            inserted = e.details.get("nInserted", 0)
            skipped = len(docs) - inserted
            logger.info(
                "data_sync.inserted_with_skips",
                inserted_count=inserted,
                skipped_duplicates=skipped,
            )
            return inserted

    async def upsert_bar(self, bar: Bar) -> None:
        """Upsert a single OHLCV bar from a domain Bar entity."""
        collection = self._collection()

        doc = bar.to_mongo()
        bar_id = doc.pop("_id", None)
        created_at = doc.pop("created_at", None)
        doc["updated_at"] = datetime.now(UTC)

        update_ops: dict = {"$set": doc}
        set_on_insert: dict = {}
        if created_at:
            set_on_insert["created_at"] = created_at
        if bar_id:
            set_on_insert["_id"] = bar_id
        if set_on_insert:
            update_ops["$setOnInsert"] = set_on_insert

        await collection.update_one(
            {
                "symbol": doc["symbol"],
                "exchange": doc["exchange"],
                "interval": doc["interval"],
                "datetime": doc["datetime"],
            },
            update_ops,
            upsert=True,
        )

    async def find(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        start_date=None,
        end_date=None,
        limit: int = 5000,
    ) -> list[Bar]:
        """Query OHLCV bars with optional date range. Returns list sorted desc by datetime."""
        collection = self._collection()

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
            records.append(Bar.from_mongo(doc))

        return records

    async def stream(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> AsyncIterator[Bar]:
        """Stream OHLCV bars for backtest. Returns async generator sorted asc by datetime."""
        collection = self._collection()

        query = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "interval": interval.value,
            "datetime": {"$gte": start_datetime, "$lte": end_datetime},
        }

        cursor = collection.find(query).sort("datetime", 1)

        try:
            async for doc in cursor:
                yield Bar.from_mongo(doc)
        finally:
            await cursor.close()

    async def count(self, symbol: str, exchange: str, interval: Interval) -> int:
        """Count documents for given symbol/exchange/interval."""
        collection = self._collection()
        return await collection.count_documents(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            }
        )

    async def get_latest(self, symbol: str, exchange: str, interval: Interval) -> Bar | None:
        """Get latest bar for symbol/exchange/interval."""
        collection = self._collection()
        doc = await collection.find_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            },
            sort=[("datetime", -1)],
        )
        return Bar.from_mongo(doc) if doc else None

    async def ensure_indexes(self) -> None:
        """Create compound index on (symbol, exchange, interval, datetime)."""
        collection = self._collection()
        await collection.create_index(
            [("symbol", 1), ("exchange", 1), ("interval", 1), ("datetime", 1)],
            unique=True,
            name="ix_ohlcv_symbol_exchange_interval_datetime",
        )
