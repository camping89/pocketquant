"""Handler for OHLCV query."""

from src.common.cache import Cache
from src.common.constants import CACHE_KEY_OHLCV, TTL_OHLCV_QUERY
from src.common.mediator import Handler, handles
from src.domain.shared.value_objects import Interval
from src.features.market_data.ohlcv.get_ohlcv.query import GetOHLCVQuery
from src.persistence.repositories.ohlcv_repository import OHLCVRepository


@handles(GetOHLCVQuery)
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

        bars = await OHLCVRepository.find(
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
