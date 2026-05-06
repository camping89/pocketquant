"""Quote feature - real-time quote feed, subscriptions, and queries."""

from pocketquant.api.market_data.handlers.quotes.dto import QuoteResult
from pocketquant.api.market_data.handlers.quotes.get_all import (
    GetAllQuotesHandler,
    GetAllQuotesQuery,
)
from pocketquant.api.market_data.handlers.quotes.get_latest import (
    GetLatestQuoteHandler,
    GetLatestQuoteQuery,
)
from pocketquant.api.market_data.handlers.quotes.get_status import (
    GetQuotesStatusHandler,
    GetQuotesStatusQuery,
)
from pocketquant.api.market_data.handlers.quotes.subscribe import (
    SubscribeCommand,
    SubscribeHandler,
)
from pocketquant.api.market_data.handlers.quotes.unsubscribe import (
    UnsubscribeCommand,
    UnsubscribeHandler,
)

__all__ = [
    # Status (observability)
    "GetQuotesStatusQuery",
    "GetQuotesStatusHandler",
    # Subscription
    "SubscribeCommand",
    "UnsubscribeCommand",
    "SubscribeHandler",
    "UnsubscribeHandler",
    # Query
    "GetLatestQuoteQuery",
    "GetAllQuotesQuery",
    "GetLatestQuoteHandler",
    "GetAllQuotesHandler",
    # DTO
    "QuoteResult",
]
