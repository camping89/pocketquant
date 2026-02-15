"""Handler for getting all active quotes."""

from src.application.market_data.quote_service import QuoteService
from src.common.constants import CACHE_KEY_QUOTE_LATEST
from src.common.mediator import Handler, handles
from src.features.market_data.quotes.dto import QuoteResult
from src.features.market_data.quotes.get_all.query import GetAllQuotesQuery
from src.persistence.redis import Cache
from src.persistence.schemas.quote_schema import Quote


@handles(GetAllQuotesQuery)
class GetAllQuotesHandler(Handler[GetAllQuotesQuery, list[QuoteResult]]):
    """Handle getting all active quotes."""

    def __init__(self, quote_service: QuoteService, cache: Cache):
        self.state = quote_service
        self._cache = cache

    async def handle(self, request: GetAllQuotesQuery) -> list[QuoteResult]:
        quotes = []
        for symbol_key in self.state.provider.subscriptions.keys():
            exchange, symbol = symbol_key.split(":", 1)
            cache_key = CACHE_KEY_QUOTE_LATEST.format(exchange=exchange, symbol=symbol)
            data = await self._cache.get(cache_key)
            if data:
                quote = Quote.from_cache_dict(data)
                quotes.append(QuoteResult.from_quote(quote))

        return quotes
