"""Handler for stopping the quote feed."""

import asyncio

from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.api.market_data.handlers.quotes.stop_feed.command import StopQuoteFeedCommand

logger = get_logger(__name__)


@handles(StopQuoteFeedCommand)
class StopQuoteFeedHandler(Handler[StopQuoteFeedCommand, dict]):
    """Handle stopping the quote feed."""

    def __init__(self, quote_app_service: QuoteAppService):
        self._quote_app_service = quote_app_service

    async def handle(self, request: StopQuoteFeedCommand) -> dict:
        if not self._quote_app_service.running:
            return {"status": "not_running", "message": "Quote service is not running"}

        logger.info("quote_service.stopping")

        saved_count = await self._quote_app_service.bar_manager.flush_all_bars()

        self._quote_app_service.running = False
        await self._quote_app_service.provider.disconnect()
        await self._cancel_ws_task()

        logger.info("quote_service.stopped")
        return {
            "status": "stopped",
            "message": "Quote service stopped",
            "bars_saved": saved_count,
        }

    async def _cancel_ws_task(self) -> None:
        if not self._quote_app_service.ws_task:
            return
        self._quote_app_service.ws_task.cancel()
        try:
            await self._quote_app_service.ws_task
        except asyncio.CancelledError:
            pass
