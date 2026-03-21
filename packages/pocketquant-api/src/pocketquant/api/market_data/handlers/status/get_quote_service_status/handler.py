"""Handler for get quote service status query."""

from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.api.market_data.handlers.status.dto import StatusResult
from pocketquant.api.market_data.handlers.status.get_quote_service_status.query import (
    GetQuoteServiceStatusQuery,
)


@handles(GetQuoteServiceStatusQuery)
class GetQuoteServiceStatusHandler(Handler[GetQuoteServiceStatusQuery, StatusResult]):
    """Handle getting quote service status."""

    def __init__(self, quote_app_service: QuoteAppService):
        self._quote_app_service = quote_app_service

    async def handle(self, request: GetQuoteServiceStatusQuery) -> StatusResult:
        return StatusResult(
            running=self._quote_app_service.running and self._quote_app_service.provider.is_connected(),
            subscription_count=self._quote_app_service.provider.subscription_count,
            active_symbols=self._quote_app_service.bar_manager.active_symbols,
        )
