"""Handler for get quote service status query."""

from src.common.mediator import Handler
from src.config import Settings
from src.features.market_data.quotes.quote_service import get_quote_service
from src.features.market_data.status.dto import StatusResult
from src.features.market_data.status.get_quote_service_status.query import (
    GetQuoteServiceStatusQuery,
)


class GetQuoteServiceStatusHandler(
    Handler[GetQuoteServiceStatusQuery, StatusResult]
):
    """Handle getting quote service status."""

    def __init__(self, settings: Settings):
        self.state = get_quote_service(settings)

    async def handle(self, request: GetQuoteServiceStatusQuery) -> StatusResult:
        return StatusResult(
            running=self.state.running and self.state.provider.is_connected(),
            subscription_count=self.state.provider.subscription_count,
            active_symbols=self.state.bar_manager.active_symbols,
        )
