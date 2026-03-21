"""Handler for starting the quote feed."""

import asyncio

from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.api.market_data.handlers.quotes.start_feed.command import StartQuoteFeedCommand

logger = get_logger(__name__)


@handles(StartQuoteFeedCommand)
class StartQuoteFeedHandler(Handler[StartQuoteFeedCommand, dict]):
    """Handle starting the quote feed."""

    def __init__(self, quote_app_service: QuoteAppService):
        self._quote_app_service = quote_app_service

    async def handle(self, request: StartQuoteFeedCommand) -> dict:
        if self._quote_app_service.running:
            logger.warning("quote_service.already_running")
            return {
                "status": "already_running",
                "message": "Quote service is already running",
            }

        logger.info("quote_service.starting")
        await self._quote_app_service.provider.connect()
        self._quote_app_service.running = True
        self._quote_app_service.ws_task = asyncio.create_task(self._quote_app_service.provider.run_forever())

        logger.info("quote_service.started")
        return {"status": "started", "message": "Quote service started"}
