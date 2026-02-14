"""Handler for starting the quote feed."""

import asyncio

from src.common.logging import get_logger
from src.common.mediator import Handler, handles
from src.config import Settings
from src.features.market_data.quotes.quote_service import get_quote_service
from src.features.market_data.quotes.start_feed.command import StartQuoteFeedCommand

logger = get_logger(__name__)


@handles(StartQuoteFeedCommand)
class StartQuoteFeedHandler(Handler[StartQuoteFeedCommand, dict]):
    """Handle starting the quote feed."""

    def __init__(self, settings: Settings):
        self.state = get_quote_service(settings)

    async def handle(self, request: StartQuoteFeedCommand) -> dict:
        if self.state.running:
            logger.warning("quote_service.already_running")
            return {
                "status": "already_running",
                "message": "Quote service is already running",
            }

        logger.info("quote_service.starting")
        await self.state.provider.connect()
        self.state.running = True
        self.state.ws_task = asyncio.create_task(self.state.provider.run_forever())

        logger.info("quote_service.started")
        return {"status": "started", "message": "Quote service started"}
