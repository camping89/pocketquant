"""Handler for getting the latest quote."""

from src.common.cache import Cache
from src.common.constants import CACHE_KEY_QUOTE_LATEST
from src.common.mediator import Handler, handles
from src.features.market_data.base.models.quote import Quote
from src.features.market_data.quotes.dto import QuoteResult
from src.features.market_data.quotes.get_latest.query import GetLatestQuoteQuery


@handles(GetLatestQuoteQuery)
class GetLatestQuoteHandler(Handler[GetLatestQuoteQuery, QuoteResult | None]):
    """Handle getting the latest quote for a symbol."""

    async def handle(self, request: GetLatestQuoteQuery) -> QuoteResult | None:
        cache_key = CACHE_KEY_QUOTE_LATEST.format(
            exchange=request.exchange.upper(), symbol=request.symbol.upper()
        )

        data = await Cache.get(cache_key)
        if data:
            quote = Quote.from_cache_dict(data)
            return QuoteResult.from_quote(quote)

        return None
