"""Handler for OHLCV query."""

from src.common.cache import Cache
from src.common.constants import CACHE_KEY_OHLCV, COLLECTION_OHLCV, TTL_OHLCV_QUERY
from src.common.database import Database
from src.common.mediator import Handler
from src.features.market_data.base.models.ohlcv import OHLCV, Interval
from src.features.market_data.ohlcv.get_ohlcv.query import GetOHLCVQuery


class GetOHLCVHandler(Handler[GetOHLCVQuery, list[dict]]):
    """Handle OHLCV data retrieval."""

    async def handle(self, request: GetOHLCVQuery) -> list[dict]:
        symbol = request.symbol.upper()
        exchange = request.exchange.upper()
        interval = Interval(request.interval)

        cache_key = CACHE_KEY_OHLCV.format(
            symbol=symbol, exchange=exchange, interval=interval.value, limit=request.limit
        )
        if request.start_date:
            cache_key += f":from:{request.start_date.isoformat()}"
        if request.end_date:
            cache_key += f":to:{request.end_date.isoformat()}"

        cached = await Cache.get(cache_key)
        if cached:
            return cached

        bars = await self._get_bars(
            symbol, exchange, interval, request.start_date, request.end_date, request.limit
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
