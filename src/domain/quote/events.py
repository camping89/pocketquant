"""Quote domain events."""

from dataclasses import dataclass
from datetime import datetime

from src.domain.shared.events import DomainEvent


@dataclass(frozen=True)
class QuoteReceived(DomainEvent):
    """Raised when a new quote tick is received."""

    symbol: str = ""
    exchange: str = ""
    price: float = 0.0
    volume: float | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True)
class QuoteUpdated(DomainEvent):
    """Raised when quote data is updated in cache."""

    symbol: str = ""
    exchange: str = ""
    last_price: float = 0.0
    change: float | None = None
    change_percent: float | None = None
