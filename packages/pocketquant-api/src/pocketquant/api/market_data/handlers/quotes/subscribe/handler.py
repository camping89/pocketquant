"""Handler for subscribing to a symbol."""

from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.api.market_data.handlers.quotes.subscribe.command import SubscribeCommand

logger = get_logger(__name__)


@handles(SubscribeCommand)
class SubscribeHandler(Handler[SubscribeCommand, dict]):
    """Handle subscribing to a symbol."""

    def __init__(self, quote_app_service: QuoteAppService):
        self._quote_app_service = quote_app_service

    async def handle(self, request: SubscribeCommand) -> dict:
        if not self._quote_app_service.running or not self._quote_app_service.provider.is_connected():
            raise ValueError("Quote service not running. Start it first via StartQuoteFeedCommand")

        symbol = request.symbol.upper()
        exchange = request.exchange.upper()

        key = await self._quote_app_service.provider.subscribe(
            symbol=symbol,
            exchange=exchange,
            callback=self._quote_app_service.on_quote_update,
        )

        logger.info("quote_service.subscribed", symbol=symbol, exchange=exchange)
        return {
            "subscription_key": key,
            "message": f"Subscribed to {key}",
        }
