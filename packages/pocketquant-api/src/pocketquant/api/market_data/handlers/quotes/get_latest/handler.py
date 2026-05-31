"""Handler for getting the latest quote."""

from pocketquant.api.market_data.app_services.quote_dto import Quote
from pocketquant.api.market_data.handlers.quotes.dto import QuoteResult
from pocketquant.api.market_data.handlers.quotes.get_latest.query import GetLatestQuoteQuery
from pocketquant.infrastructure.persistence import Cache
from pocketquant.core.common.constants import CACHE_KEY_QUOTE_LATEST
from pocketquant.core.common.mediator import Handler, handles


@handles(GetLatestQuoteQuery)
class GetLatestQuoteHandler(Handler[GetLatestQuoteQuery, QuoteResult | None]):
    """Handle getting the latest quote for a composite symbol."""

    def __init__(self, cache: Cache):
        self._cache = cache

    async def handle(self, request: GetLatestQuoteQuery) -> QuoteResult | None:
        cache_key = CACHE_KEY_QUOTE_LATEST.format(symbol=request.symbol.upper())

        data = await self._cache.get(cache_key)
        if data:
            quote = Quote.from_cache_dict(data)
            return QuoteResult.from_quote(quote)

        return None
