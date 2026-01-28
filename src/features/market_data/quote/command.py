"""Quote commands."""

from dataclasses import dataclass


@dataclass
class SubscribeCommand:
    """Subscribe to real-time quotes for a symbol."""

    symbol: str
    exchange: str


@dataclass
class UnsubscribeCommand:
    """Unsubscribe from real-time quotes for a symbol."""

    symbol: str
    exchange: str


@dataclass
class StartQuoteFeedCommand:
    """Start the quote WebSocket feed."""

    pass


@dataclass
class StopQuoteFeedCommand:
    """Stop the quote WebSocket feed."""

    pass
