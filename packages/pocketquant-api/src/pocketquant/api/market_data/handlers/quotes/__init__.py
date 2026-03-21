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
from pocketquant.api.market_data.handlers.quotes.start_feed import (
    StartQuoteFeedCommand,
    StartQuoteFeedHandler,
)
from pocketquant.api.market_data.handlers.quotes.stop_feed import (
    StopQuoteFeedCommand,
    StopQuoteFeedHandler,
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
    # Feed
    "StartQuoteFeedCommand",
    "StopQuoteFeedCommand",
    "StartQuoteFeedHandler",
    "StopQuoteFeedHandler",
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
