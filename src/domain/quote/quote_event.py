"""Quote domain events."""

from datetime import datetime

from src.domain.shared.domain_event import DomainEvent


class QuoteReceivedEvent(DomainEvent):
    """Raised when a new quote tick is received."""

    symbol: str = ""
    exchange: str = ""
    price: float = 0.0
    volume: float | None = None
    timestamp: datetime | None = None


class QuoteUpdatedEvent(DomainEvent):
    """Raised when quote data is updated in cache."""

    symbol: str = ""
    exchange: str = ""
    last_price: float = 0.0
    change: float | None = None
    change_percent: float | None = None
