"""Handler for subscribing to a symbol."""

from src.application.market_data.quote_service import QuoteService
from src.common.logging import get_logger
from src.common.mediator import Handler, handles
from src.features.market_data.quotes.subscribe.command import SubscribeCommand

logger = get_logger(__name__)


@handles(SubscribeCommand)
class SubscribeHandler(Handler[SubscribeCommand, dict]):
    """Handle subscribing to a symbol."""

    def __init__(self, quote_service: QuoteService):
        self.state = quote_service

    async def handle(self, request: SubscribeCommand) -> dict:
        if not self.state.running or not self.state.provider.is_connected():
            raise ValueError("Quote service not running. Start it first via StartQuoteFeedCommand")

        symbol = request.symbol.upper()
        exchange = request.exchange.upper()

        key = await self.state.provider.subscribe(
            symbol=symbol,
            exchange=exchange,
            callback=self.state.on_quote_update,
        )

        logger.info("quote_service.subscribed", symbol=symbol, exchange=exchange)
        return {
            "subscription_key": key,
            "message": f"Subscribed to {key}",
        }
