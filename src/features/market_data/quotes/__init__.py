"""Quote feature - real-time quote feed, subscriptions, and queries."""

from src.features.market_data.quotes.dto import QuoteResult
from src.features.market_data.quotes.get_all import (
    GetAllQuotesHandler,
    GetAllQuotesQuery,
)
from src.features.market_data.quotes.get_latest import (
    GetLatestQuoteHandler,
    GetLatestQuoteQuery,
)
from src.features.market_data.quotes.start_feed import (
    StartQuoteFeedCommand,
    StartQuoteFeedHandler,
)
from src.features.market_data.quotes.stop_feed import (
    StopQuoteFeedCommand,
    StopQuoteFeedHandler,
)
from src.features.market_data.quotes.subscribe import (
    SubscribeCommand,
    SubscribeHandler,
)
from src.features.market_data.quotes.unsubscribe import (
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
