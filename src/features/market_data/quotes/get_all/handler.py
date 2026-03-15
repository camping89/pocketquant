"""Handler for getting all active quotes."""

from src.application.market_data.quote_app_service import QuoteAppService
from src.application.market_data.quote_dto import Quote
from src.common.constants import CACHE_KEY_QUOTE_LATEST
from src.common.mediator import Handler, handles
from src.features.market_data.quotes.dto import QuoteResult
from src.features.market_data.quotes.get_all.query import GetAllQuotesQuery
from src.persistence.redis import Cache


@handles(GetAllQuotesQuery)
class GetAllQuotesHandler(Handler[GetAllQuotesQuery, list[QuoteResult]]):
    """Handle getting all active quotes."""

    def __init__(self, quote_service: QuoteAppService, cache: Cache):
        self.state = quote_service
        self._cache = cache

    async def handle(self, request: GetAllQuotesQuery) -> list[QuoteResult]:
        symbol_keys = list(self.state.provider.subscriptions.keys())
        cache_keys = [
            CACHE_KEY_QUOTE_LATEST.format(
                exchange=key.split(":", 1)[0], symbol=key.split(":", 1)[1]
            )
            for key in symbol_keys
        ]

        cached_values = await self._cache.mget(cache_keys)

        quotes = []
        for data in cached_values:
            if data:
                quote = Quote.from_cache_dict(data)
                quotes.append(QuoteResult.from_quote(quote))

        return quotes
