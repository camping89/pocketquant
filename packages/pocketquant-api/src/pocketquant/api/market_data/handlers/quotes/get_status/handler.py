"""Handler for GET /quotes/status — returns WS feed health metrics."""

from dataclasses import dataclass
from datetime import UTC, datetime

from pocketquant.api.market_data.handlers.quotes.get_status.query import GetQuotesStatusQuery
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.infrastructure.realtime_quote_provider import IRealtimeQuoteProvider


@dataclass
class QuotesStatusResult:
    """Result DTO for /quotes/status."""

    connected: bool
    subscribed_count: int
    last_tick_at: datetime | None
    lag_seconds: float | None


@handles(GetQuotesStatusQuery)
class GetQuotesStatusHandler(Handler[GetQuotesStatusQuery, QuotesStatusResult]):
    """Handle GET /quotes/status — reads provider state directly (no DB)."""

    def __init__(self, provider: IRealtimeQuoteProvider):
        self._provider = provider

    async def handle(self, request: GetQuotesStatusQuery) -> QuotesStatusResult:
        last_tick_at = self._provider.last_tick_at
        lag_seconds: float | None = None

        if last_tick_at is not None:
            lag_seconds = (datetime.now(UTC) - last_tick_at).total_seconds()

        return QuotesStatusResult(
            connected=self._provider.is_connected(),
            subscribed_count=len(self._provider.subscriptions),
            last_tick_at=last_tick_at,
            lag_seconds=lag_seconds,
        )
