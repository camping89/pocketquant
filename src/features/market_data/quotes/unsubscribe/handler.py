"""Handler for unsubscribing from a symbol."""

from src.common.cache import Cache
from src.common.constants import CACHE_KEY_QUOTE_LATEST
from src.common.logging import get_logger
from src.common.mediator import Handler, handles
from src.config import Settings
from src.features.market_data.quotes.quote_service import get_quote_service
from src.features.market_data.quotes.unsubscribe.command import UnsubscribeCommand

logger = get_logger(__name__)


@handles(UnsubscribeCommand)
class UnsubscribeHandler(Handler[UnsubscribeCommand, dict]):
    """Handle unsubscribing from a symbol."""

    def __init__(self, settings: Settings):
        self.state = get_quote_service(settings)

    async def handle(self, request: UnsubscribeCommand) -> dict:
        symbol = request.symbol.upper()
        exchange = request.exchange.upper()

        await self.state.provider.unsubscribe(symbol, exchange)
        cache_key = CACHE_KEY_QUOTE_LATEST.format(exchange=exchange, symbol=symbol)
        await Cache.delete(cache_key)

        logger.info("quote_service.unsubscribed", symbol=symbol, exchange=exchange)
        return {"message": f"Unsubscribed from {exchange}:{symbol}"}
