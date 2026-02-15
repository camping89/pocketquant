"""Handler for unsubscribing from a symbol."""

from src.application.market_data.quote_service import QuoteService
from src.common.constants import CACHE_KEY_QUOTE_LATEST
from src.common.logging import get_logger
from src.common.mediator import Handler, handles
from src.features.market_data.quotes.unsubscribe.command import UnsubscribeCommand
from src.persistence.redis import Cache

logger = get_logger(__name__)


@handles(UnsubscribeCommand)
class UnsubscribeHandler(Handler[UnsubscribeCommand, dict]):
    """Handle unsubscribing from a symbol."""

    def __init__(self, quote_service: QuoteService, cache: Cache):
        self.state = quote_service
        self._cache = cache

    async def handle(self, request: UnsubscribeCommand) -> dict:
        symbol = request.symbol.upper()
        exchange = request.exchange.upper()

        await self.state.provider.unsubscribe(symbol, exchange)
        cache_key = CACHE_KEY_QUOTE_LATEST.format(exchange=exchange, symbol=symbol)
        await self._cache.delete(cache_key)

        logger.info("quote_service.unsubscribed", symbol=symbol, exchange=exchange)
        return {"message": f"Unsubscribed from {exchange}:{symbol}"}
