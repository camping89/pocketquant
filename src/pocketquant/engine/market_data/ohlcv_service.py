"""OHLCV query service — cached bar retrieval for a composite symbol."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pocketquant.core.common.constants import CACHE_KEY_OHLCV, TTL_OHLCV_QUERY
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository


@dataclass
class GetOHLCVQuery:
    """Query to retrieve OHLCV bars for a composite symbol.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    symbol: str
    interval: str = "1d"
    limit: int = 1000
    start_date: datetime | None = None
    end_date: datetime | None = None


@dataclass
class OHLCVResponse:
    """Result of OHLCV query. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    interval: str
    data: list[dict[str, Any]]
    count: int


class OhlcvService:
    """Cached OHLCV retrieval for a composite symbol."""

    def __init__(self, cache: Cache, bar_repository: BarRepository) -> None:
        self._cache = cache
        self._bar_repo = bar_repository

    async def get_ohlcv(self, request: GetOHLCVQuery) -> OHLCVResponse:
        """Return OHLCV bars for ``symbol`` at ``interval``, using cache when warm."""
        symbol = request.symbol.upper()
        interval = Interval(request.interval)

        cache_key = self._build_cache_key(symbol, interval, request)
        cached = await self._cache.get(cache_key)
        if cached:
            return OHLCVResponse(
                symbol=symbol,
                interval=interval.value,
                data=cached,
                count=len(cached),
            )

        bars = await self._bar_repo.find(
            symbol, interval, request.start_date, request.end_date, request.limit
        )

        data = [
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

        await self._cache.set(cache_key, data, ttl=TTL_OHLCV_QUERY)

        return OHLCVResponse(symbol=symbol, interval=interval.value, data=data, count=len(data))

    @staticmethod
    def _build_cache_key(symbol: str, interval: Interval, request: GetOHLCVQuery) -> str:
        key = CACHE_KEY_OHLCV.format(symbol=symbol, interval=interval.value, limit=request.limit)
        if request.start_date:
            key += f":from:{request.start_date.isoformat()}"
        if request.end_date:
            key += f":to:{request.end_date.isoformat()}"
        return key
