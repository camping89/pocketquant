"""Handler for get quote service status query."""

from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.api.market_data.handlers.status.dto import StatusResult
from pocketquant.api.market_data.handlers.status.get_quote_service_status.query import (
    GetQuoteServiceStatusQuery,
)
from pocketquant.core.common.mediator import Handler, handles


@handles(GetQuoteServiceStatusQuery)
class GetQuoteServiceStatusHandler(Handler[GetQuoteServiceStatusQuery, StatusResult]):
    """Handle getting quote service status."""

    def __init__(self, quote_app_service: QuoteAppService):
        self._quote_app_service = quote_app_service

    async def handle(self, request: GetQuoteServiceStatusQuery) -> StatusResult:
        svc = self._quote_app_service
        return StatusResult(
            running=svc.running and svc.provider.is_connected(),
            subscription_count=svc.provider.subscription_count,
            active_symbols=svc.bar_manager.active_symbols,
        )
