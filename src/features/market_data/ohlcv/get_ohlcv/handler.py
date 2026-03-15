"""Handler for OHLCV query."""

from src.common.cache import Cache
from src.common.constants import CACHE_KEY_OHLCV, TTL_OHLCV_QUERY
from src.common.mediator import Handler, handles
from src.domain.shared.value_objects import Interval
from src.features.market_data.ohlcv.get_ohlcv.query import GetOHLCVQuery
from src.persistence.repositories.bar_repository import BarRepository


@handles(GetOHLCVQuery)
class GetOHLCVHandler(Handler[GetOHLCVQuery, list[dict]]):
    """Handle OHLCV data retrieval."""

    def __init__(self, cache: Cache, bar_repository: BarRepository):
        self._cache = cache
        self._bar_repo = bar_repository

    async def handle(self, request: GetOHLCVQuery) -> list[dict]:
        symbol = request.symbol.upper()
        exchange = request.exchange.upper()
        interval = Interval(request.interval)

        cache_key = self._build_cache_key(symbol, exchange, interval, request)

        cached = await self._cache.get(cache_key)
        if cached:
            return cached

        bars = await self._bar_repo.find(
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

        await self._cache.set(cache_key, result, ttl=TTL_OHLCV_QUERY)

        return result

    @staticmethod
    def _build_cache_key(
        symbol: str, exchange: str, interval: Interval, request: GetOHLCVQuery
    ) -> str:
        key = CACHE_KEY_OHLCV.format(
            symbol=symbol, exchange=exchange, interval=interval.value, limit=request.limit
        )
        if request.start_date:
            key += f":from:{request.start_date.isoformat()}"
        if request.end_date:
            key += f":to:{request.end_date.isoformat()}"
        return key
