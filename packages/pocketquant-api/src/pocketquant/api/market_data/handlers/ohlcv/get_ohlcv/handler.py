"""Handler for OHLCV query."""

from pocketquant.api.market_data.handlers.ohlcv.get_ohlcv.query import GetOHLCVQuery
from pocketquant.core.common.cache import Cache
from pocketquant.core.common.constants import CACHE_KEY_OHLCV, TTL_OHLCV_QUERY
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.shared.value_objects import Interval
from pocketquant.core.persistence.repositories.bar_repository import BarRepository


@handles(GetOHLCVQuery)
class GetOHLCVHandler(Handler[GetOHLCVQuery, list[dict]]):
    """Handle OHLCV data retrieval. ``symbol`` is composite ``{code}:{exchange}``."""

    def __init__(self, cache: Cache, bar_repository: BarRepository):
        self._cache = cache
        self._bar_repo = bar_repository

    async def handle(self, request: GetOHLCVQuery) -> list[dict]:
        symbol = request.symbol.upper()
        interval = Interval(request.interval)

        cache_key = self._build_cache_key(symbol, interval, request)

        cached = await self._cache.get(cache_key)
        if cached:
            return cached

        bars = await self._bar_repo.find(
            symbol, interval, request.start_date, request.end_date, request.limit
        )

        result = [
            {
                "id": str(bar.id),
                "datetime": bar.datetime.isoformat() if bar.datetime else None,
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
    def _build_cache_key(symbol: str, interval: Interval, request: GetOHLCVQuery) -> str:
        key = CACHE_KEY_OHLCV.format(
            symbol=symbol, interval=interval.value, limit=request.limit
        )
        if request.start_date:
            key += f":from:{request.start_date.isoformat()}"
        if request.end_date:
            key += f":to:{request.end_date.isoformat()}"
        return key
