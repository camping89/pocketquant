"""Handler for subscribing to a symbol."""

from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.api.market_data.handlers.quotes.subscribe.command import SubscribeCommand
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles

logger = get_logger(__name__)


@handles(SubscribeCommand)
class SubscribeHandler(Handler[SubscribeCommand, dict]):
    """Handle subscribing to a composite symbol."""

    def __init__(self, quote_app_service: QuoteAppService):
        self._quote_app_service = quote_app_service

    async def handle(self, request: SubscribeCommand) -> dict:
        svc = self._quote_app_service
        if not svc.running or not svc.provider.is_connected():
            raise ValueError("Quote service not running. Start it first via StartQuoteFeedCommand")

        symbol = request.symbol.upper()

        key = await self._quote_app_service.provider.subscribe(
            symbol=symbol,
            callback=self._quote_app_service.on_quote_update,
        )

        logger.info("quote_service.subscribed", symbol=symbol)
        return {
            "subscription_key": key,
            "message": f"Subscribed to {key}",
        }
