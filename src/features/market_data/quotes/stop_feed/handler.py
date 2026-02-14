"""Handler for stopping the quote feed."""

import asyncio

from src.application.market_data.quote_service import get_quote_service
from src.common.logging import get_logger
from src.common.mediator import Handler, handles
from src.config import Settings
from src.features.market_data.quotes.stop_feed.command import StopQuoteFeedCommand

logger = get_logger(__name__)


@handles(StopQuoteFeedCommand)
class StopQuoteFeedHandler(Handler[StopQuoteFeedCommand, dict]):
    """Handle stopping the quote feed."""

    def __init__(self, settings: Settings):
        self.state = get_quote_service(settings)

    async def handle(self, request: StopQuoteFeedCommand) -> dict:
        if not self.state.running:
            return {"status": "not_running", "message": "Quote service is not running"}

        logger.info("quote_service.stopping")

        saved_count = await self.state.bar_manager.flush_all_bars()

        self.state.running = False
        await self.state.provider.disconnect()

        if self.state.ws_task:
            self.state.ws_task.cancel()
            try:
                await self.state.ws_task
            except asyncio.CancelledError:
                pass

        logger.info("quote_service.stopped")
        return {
            "status": "stopped",
            "message": "Quote service stopped",
            "bars_saved": saved_count,
        }
