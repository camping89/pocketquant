"""Handler for getting the latest quote."""

from src.application.market_data.quote_dto import Quote
from src.common.cache import Cache
from src.common.constants import CACHE_KEY_QUOTE_LATEST
from src.common.mediator import Handler, handles
from src.features.market_data.quotes.dto import QuoteResult
from src.features.market_data.quotes.get_latest.query import GetLatestQuoteQuery


@handles(GetLatestQuoteQuery)
class GetLatestQuoteHandler(Handler[GetLatestQuoteQuery, QuoteResult | None]):
    """Handle getting the latest quote for a symbol."""

    def __init__(self, cache: Cache):
        self._cache = cache

    async def handle(self, request: GetLatestQuoteQuery) -> QuoteResult | None:
        cache_key = CACHE_KEY_QUOTE_LATEST.format(
            exchange=request.exchange.upper(), symbol=request.symbol.upper()
        )

        data = await self._cache.get(cache_key)
        if data:
            quote = Quote.from_cache_dict(data)
            return QuoteResult.from_quote(quote)

        return None
