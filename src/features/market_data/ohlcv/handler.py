"""Handler for OHLCV queries."""

from src.common.cache import Cache
from src.common.constants import CACHE_KEY_OHLCV, COLLECTION_OHLCV, TTL_OHLCV_QUERY
from src.common.database import Database
from src.common.mediator import Handler
from src.features.market_data.models.ohlcv import OHLCV, Interval
from src.features.market_data.ohlcv.query import GetOHLCVQuery


class GetOHLCVHandler(Handler[GetOHLCVQuery, list[dict]]):
    """Handle OHLCV data retrieval."""

    async def handle(self, query: GetOHLCVQuery) -> list[dict]:
        symbol = query.symbol.upper()
        exchange = query.exchange.upper()
        interval = Interval(query.interval)

        cache_key = CACHE_KEY_OHLCV.format(
            symbol=symbol, exchange=exchange, interval=interval.value, limit=query.limit
        )
        if query.start_date:
            cache_key += f":from:{query.start_date.isoformat()}"
        if query.end_date:
            cache_key += f":to:{query.end_date.isoformat()}"

        cached = await Cache.get(cache_key)
        if cached:
            return cached

        bars = await self._get_bars(
            symbol, exchange, interval, query.start_date, query.end_date, query.limit
        )

        result = [
            {
                "datetime": bar.datetime.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]

        await Cache.set(cache_key, result, ttl=TTL_OHLCV_QUERY)

        return result

    async def _get_bars(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        start_date,
        end_date,
        limit: int,
    ) -> list[OHLCV]:
        collection = Database.get_collection(COLLECTION_OHLCV)

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
