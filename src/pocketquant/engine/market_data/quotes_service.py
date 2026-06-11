"""Quote query service — latest quote lookup from Redis cache."""

from pydantic import BaseModel

from pocketquant.core.common.constants import CACHE_KEY_QUOTE_LATEST
from pocketquant.core.infra.persistence import Cache
from pocketquant.engine.market_data.app_services.quote_dto import Quote


class GetLatestQuoteQuery(BaseModel):
    """Get the latest quote. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str


class QuoteResponse(BaseModel):
    """``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    timestamp: str
    last_price: float
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None

    @classmethod
    def from_quote(cls, quote: Quote) -> QuoteResponse:
        return cls(
            symbol=quote.symbol,
            timestamp=quote.timestamp.isoformat(),
            last_price=quote.last_price,
            bid=quote.bid,
            ask=quote.ask,
            volume=quote.volume,
            change=quote.change,
            change_percent=quote.change_percent,
            open_price=quote.open_price,
            high_price=quote.high_price,
            low_price=quote.low_price,
        )


class QuoteQueryService:
    """Latest-quote lookup from Redis; returns None when symbol not yet published."""

    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    async def get_latest(self, request: GetLatestQuoteQuery) -> QuoteResponse | None:
        """Return the latest quote for a composite symbol, or None if not in cache."""
        cache_key = CACHE_KEY_QUOTE_LATEST.format(symbol=request.symbol.upper())
        data = await self._cache.get(cache_key)
        if data:
            quote = Quote.from_cache_dict(data)
            return QuoteResponse.from_quote(quote)
        return None
