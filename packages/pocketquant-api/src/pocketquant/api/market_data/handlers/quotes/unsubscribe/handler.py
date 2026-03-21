"""Handler for unsubscribing from a symbol."""

from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.core.common.constants import CACHE_KEY_QUOTE_LATEST
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.api.market_data.handlers.quotes.unsubscribe.command import UnsubscribeCommand
from pocketquant.core.persistence.redis import Cache

logger = get_logger(__name__)


@handles(UnsubscribeCommand)
class UnsubscribeHandler(Handler[UnsubscribeCommand, dict]):
    """Handle unsubscribing from a symbol."""

    def __init__(self, quote_app_service: QuoteAppService, cache: Cache):
        self._quote_app_service = quote_app_service
        self._cache = cache

    async def handle(self, request: UnsubscribeCommand) -> dict:
        symbol = request.symbol.upper()
        exchange = request.exchange.upper()

        await self._quote_app_service.provider.unsubscribe(symbol, exchange)
        cache_key = CACHE_KEY_QUOTE_LATEST.format(exchange=exchange, symbol=symbol)
        await self._cache.delete(cache_key)

        logger.info("quote_service.unsubscribed", symbol=symbol, exchange=exchange)
        return {"message": f"Unsubscribed from {exchange}:{symbol}"}
