"""OHLCV repository for MongoDB persistence."""

from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from src.common.constants import COLLECTION_OHLCV
from src.common.logging import get_logger
from src.domain.ohlcv.entities import Bar
from src.domain.shared.value_objects import Interval
from src.persistence.base_repository import BaseRepository
from src.persistence.schemas.ohlcv_schema import OHLCV, OHLCVBase

logger = get_logger(__name__)


def _doc_to_bar(doc: dict) -> Bar:
    """Convert a MongoDB document to a domain Bar entity."""
    interval_val = doc.get("interval")
    if isinstance(interval_val, str):
        interval_val = Interval(interval_val)

    raw_id = doc.get("_id", "")
    bar_id = UUID(str(raw_id)) if raw_id else None

    return Bar(
        **({"id": bar_id} if bar_id else {}),
        symbol=doc.get("symbol", ""),
        exchange=doc.get("exchange", ""),
        interval=interval_val,
        datetime=doc.get("datetime"),
        open=doc.get("open", 0.0),
        high=doc.get("high", 0.0),
        low=doc.get("low", 0.0),
        close=doc.get("close", 0.0),
        volume=doc.get("volume", 0.0),
    )


class OHLCVRepository(BaseRepository):
    """Repository for OHLCV bar data operations."""

    _collection_name = COLLECTION_OHLCV

    async def upsert_many(self, records: list[OHLCVBase]) -> int:
        """Bulk upsert OHLCV records. Returns count of upserted + modified."""
        if not records:
            return 0

        collection = self._collection()
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

        try:
            result = await collection.bulk_write(operations, ordered=False)
            total = result.upserted_count + result.modified_count

            logger.info(
                "data_sync.upserted",
                upserted_count=result.upserted_count,
                modified_count=result.modified_count,
                total_count=total,
            )

            return total
        except BulkWriteError as e:
            logger.error(
                "ohlcv_bulk_write_partial_failure",
                write_errors=len(e.details.get("writeErrors", [])),
                total_ops=len(operations),
            )
            raise

    async def upsert_bar(self, bar: Bar) -> None:
        """Upsert a single OHLCV bar from a domain Bar entity."""
        collection = self._collection()

        ohlcv = OHLCV(
            symbol=bar.symbol,
            exchange=bar.exchange,
            interval=bar.interval,
            datetime=bar.datetime,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        doc = ohlcv.to_mongo()
        created_at = doc.pop("created_at", None)

        update_ops: dict = {"$set": doc}
        if created_at:
            update_ops["$setOnInsert"] = {"created_at": created_at}

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
            records.append(_doc_to_bar(doc))

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
                yield _doc_to_bar(doc)
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
        return _doc_to_bar(doc) if doc else None

    async def ensure_indexes(self) -> None:
        """Create compound index on (symbol, exchange, interval, datetime)."""
        collection = self._collection()
        await collection.create_index(
            [("symbol", 1), ("exchange", 1), ("interval", 1), ("datetime", 1)],
            unique=True,
            name="ix_ohlcv_symbol_exchange_interval_datetime",
        )
