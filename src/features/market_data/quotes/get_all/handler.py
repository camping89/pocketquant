"""Handler for getting all active quotes."""

from src.common.cache import Cache
from src.common.constants import CACHE_KEY_QUOTE_LATEST
from src.common.mediator import Handler, handles
from src.config import Settings
from src.features.market_data.base.models.quote import Quote
from src.features.market_data.quotes.dto import QuoteResult
from src.features.market_data.quotes.get_all.query import GetAllQuotesQuery
from src.features.market_data.quotes.quote_service import get_quote_service


@handles(GetAllQuotesQuery)
class GetAllQuotesHandler(Handler[GetAllQuotesQuery, list[QuoteResult]]):
    """Handle getting all active quotes."""

    def __init__(self, settings: Settings):
        self.state = get_quote_service(settings)

    async def handle(self, request: GetAllQuotesQuery) -> list[QuoteResult]:
        quotes = []
        for symbol_key in self.state.provider.subscriptions.keys():
            exchange, symbol = symbol_key.split(":", 1)
            cache_key = CACHE_KEY_QUOTE_LATEST.format(exchange=exchange, symbol=symbol)
            data = await Cache.get(cache_key)
            if data:
                quote = Quote.from_cache_dict(data)
                quotes.append(QuoteResult.from_quote(quote))

        return quotes
