"""Handler for getting all active quotes."""

from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.api.market_data.app_services.quote_dto import Quote
from pocketquant.api.market_data.handlers.quotes.dto import QuoteResult
from pocketquant.api.market_data.handlers.quotes.get_all.query import GetAllQuotesQuery
from pocketquant.core.common.constants import CACHE_KEY_QUOTE_LATEST
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.persistence.redis import Cache


@handles(GetAllQuotesQuery)
class GetAllQuotesHandler(Handler[GetAllQuotesQuery, list[QuoteResult]]):
    """Handle getting all active quotes. Subscription keys are composite symbols."""

    def __init__(self, quote_app_service: QuoteAppService, cache: Cache):
        self._quote_app_service = quote_app_service
        self._cache = cache

    async def handle(self, request: GetAllQuotesQuery) -> list[QuoteResult]:
        # provider.subscriptions keys are composite symbols (e.g. BTCUSDT:BINANCE)
        symbol_keys = list(self._quote_app_service.provider.subscriptions.keys())
        cache_keys = [CACHE_KEY_QUOTE_LATEST.format(symbol=key) for key in symbol_keys]

        cached_values = await self._cache.mget(cache_keys)

        quotes = []
        for data in cached_values:
            if data:
                quote = Quote.from_cache_dict(data)
                quotes.append(QuoteResult.from_quote(quote))

        return quotes
