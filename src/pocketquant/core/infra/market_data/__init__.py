"""Provider-routing adapters — one port, many concrete market-data providers.

These implement the same ports their children do, so every consumer
(``SyncService``, ``fetch_with_retry``, ``WsSubscriptionAppService``,
``QuoteAppService``, ``TrackedSymbolBackfillService``) stays unaware that more
than one provider exists.
"""

from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    RoutingDataProviderAdapter,
)
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import (
    RoutingRealtimeQuoteAdapter,
)

__all__ = ["RoutingDataProviderAdapter", "RoutingRealtimeQuoteAdapter"]
