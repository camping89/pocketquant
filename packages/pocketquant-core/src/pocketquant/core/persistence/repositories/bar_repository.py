"""Bar repository for MongoDB persistence."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from cachetools import TTLCache
from pocketquant.core.common.constants import COLLECTION_BARS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.persistence.base_repository import BaseRepository

logger = get_logger(__name__)

# Module-level cache to deduplicate writes across cascade re-runs.
# Process-local — restart triggers a cold window (~5 cascade ticks to warm up).
# Key:   (symbol_composite_upper, interval_value, datetime_iso_utc)
# Value: (open, high, low, close, volume)  — tick_count excluded by design.
_BAR_VALUE_CACHE: TTLCache = TTLCache(maxsize=20_000, ttl=3600)


def _cache_key(bar: Bar) -> tuple[str, str, str]:
    interval_val = bar.interval.value if bar.interval else ""
    dt_iso = bar.datetime.isoformat() if bar.datetime else ""
    return (
        bar.symbol.upper(),
        interval_val,
        dt_iso,
    )


def _cache_value(bar: Bar) -> tuple[float, float, float, float, float]:
    return (bar.open, bar.high, bar.low, bar.close, bar.volume)


class BarRepository(BaseRepository):
    """Repository for bar data operations. ``symbol`` is composite ``{code}:{exchange}``."""

    _collection_name = COLLECTION_BARS

    async def insert_many(self, records: list[Bar], *, source: str) -> int:
        """Upsert each bar via upsert_bar. Returns count of upserts attempted successfully.

        Loop ensures in-progress bars (e.g. building 1m) get refreshed, unlike the
        previous insert_many(ordered=False) which silently skipped duplicates.
        """
        if not records:
            return 0
        count = 0
        for bar in records:
            try:
                await self.upsert_bar(bar, source=source)
                count += 1
            except Exception:
                logger.error(
                    "bar_repo.insert_many.upsert_failed",
                    symbol=bar.symbol,
                    datetime=str(bar.datetime),
                    source=source,
                    exc_info=True,
                )
        logger.info(
            "bar_repo.insert_many.completed",
            attempted=len(records),
            upserted=count,
            source=source,
        )
        return count

    async def upsert_bar(self, bar: Bar, *, source: str) -> None:
        """Diff-aware upsert. Only bumps updated_at when OHLCV actually changes.

        Three branches:
        1. Cache hit + same OHLCV   → no DB IO.
        2. DB miss (new doc)        → $setOnInsert _id/created_at, $set OHLCV+updated_at+source.
        3. DB has same OHLCV        → warm cache, no write.
        4. DB has different OHLCV   → $set OHLCV+updated_at+source (created_at preserved).
        """
        key = _cache_key(bar)
        new_value = _cache_value(bar)

        cached = _BAR_VALUE_CACHE.get(key)
        if cached == new_value:
            return

        collection = self._collection()
        now = datetime.now(UTC)
        filter_q = {
            "symbol": bar.symbol.upper(),
            "interval": bar.interval.value if bar.interval else None,
            "datetime": bar.datetime,
        }

        existing = await collection.find_one(
            filter_q,
            {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        )

        if existing is None:
            doc = bar.to_mongo()
            bar_id = doc.pop("_id")
            created_at = doc.pop("created_at")
            await collection.update_one(
                filter_q,
                {
                    "$setOnInsert": {
                        "_id": bar_id,
                        "created_at": created_at,
                    },
                    "$set": {**doc, "updated_at": now, "source": source},
                },
                upsert=True,
            )
            _BAR_VALUE_CACHE[key] = new_value
            return

        existing_value = (
            existing.get("open", 0.0),
            existing.get("high", 0.0),
            existing.get("low", 0.0),
            existing.get("close", 0.0),
            existing.get("volume", 0.0),
        )
        if existing_value == new_value:
            _BAR_VALUE_CACHE[key] = new_value
            return

        await collection.update_one(
            filter_q,
            {
                "$set": {
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "tick_count": bar.tick_count,
                    "updated_at": now,
                    "source": source,
                },
            },
        )
        _BAR_VALUE_CACHE[key] = new_value

    async def find(
        self,
        symbol: str,
        interval: Interval,
        start_date=None,
        end_date=None,
        limit: int = 5000,
    ) -> list[Bar]:
        """Query OHLCV bars with optional date range. Returns list sorted desc by datetime."""
        collection = self._collection()

        query: dict = {
            "symbol": symbol.upper(),
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
        interval: Interval,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> AsyncIterator[Bar]:
        """Stream OHLCV bars for backtest. Returns async generator sorted asc by datetime."""
        collection = self._collection()

        query = {
            "symbol": symbol.upper(),
            "interval": interval.value,
            "datetime": {"$gte": start_datetime, "$lte": end_datetime},
        }

        cursor = collection.find(query).sort("datetime", 1)

        try:
            async for doc in cursor:
                yield Bar.from_mongo(doc)
        finally:
            await cursor.close()

    async def count(self, symbol: str, interval: Interval) -> int:
        """Count documents for given symbol/interval."""
        collection = self._collection()
        return await collection.count_documents(
            {
                "symbol": symbol.upper(),
                "interval": interval.value,
            }
        )

    async def get_latest(self, symbol: str, interval: Interval) -> Bar | None:
        """Get latest bar for symbol/interval."""
        collection = self._collection()
        doc = await collection.find_one(
            {
                "symbol": symbol.upper(),
                "interval": interval.value,
            },
            sort=[("datetime", -1)],
        )
        return Bar.from_mongo(doc) if doc else None

    async def find_datetimes(
        self,
        symbol: str,
        interval: Interval,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """Return lightweight [{_id, datetime}] sorted asc for integrity scanning."""
        query: dict = {
            "symbol": symbol.upper(),
            "interval": interval.value,
        }
        if start_date or end_date:
            query["datetime"] = {}
            if start_date:
                query["datetime"]["$gte"] = start_date
            if end_date:
                query["datetime"]["$lte"] = end_date
        cursor = (
            self._collection()
            .find(query, {"_id": 1, "datetime": 1})
            .sort("datetime", 1)
            .limit(100_000)
        )
        return [doc async for doc in cursor]

    async def delete_many_by_ids(self, ids: list[str]) -> int:
        """Bulk delete bars by _id list."""
        if not ids:
            return 0
        result = await self._collection().delete_many({"_id": {"$in": ids}})
        return result.deleted_count

    async def delete_many_by_range(
        self,
        symbol: str,
        intervals: list[Interval],
        start_dt: datetime,
        end_dt: datetime,
    ) -> int:
        """Delete bars for symbol within [start_dt, end_dt) for the given intervals.

        Returns the total deleted_count. Passing an empty intervals list is a no-op (returns 0).
        Uses $in filter so multiple intervals are deleted in a single round-trip.
        """
        if not intervals:
            logger.warning("delete_many_by_range.no_intervals", symbol=symbol)
            return 0

        result = await self._collection().delete_many(
            {
                "symbol": symbol.upper(),
                "interval": {"$in": [i.value for i in intervals]},
                "datetime": {"$gte": start_dt, "$lt": end_dt},
            }
        )
        deleted = result.deleted_count
        logger.info(
            "bar_repo.delete_many_by_range",
            symbol=symbol,
            intervals=[i.value for i in intervals],
            start_dt=start_dt.isoformat(),
            end_dt=end_dt.isoformat(),
            deleted_count=deleted,
        )
        return deleted

    async def ensure_indexes(self) -> None:
        """Create unique compound index on (symbol, interval, datetime)."""
        collection = self._collection()
        await collection.create_index(
            [("symbol", 1), ("interval", 1), ("datetime", 1)],
            unique=True,
            name="ix_ohlcv_symbol_interval_datetime",
        )
