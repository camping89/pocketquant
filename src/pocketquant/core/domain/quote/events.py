from dataclasses import dataclass
from datetime import datetime

from pocketquant.core.domain.shared.events import DomainEvent


@dataclass(frozen=True, eq=False)
class QuoteReceivedEvent(DomainEvent):
    """Raised when a new quote tick is received.

    ``symbol`` is composite ``{code}:{exchange}``.
    """

    symbol: str = ""
    price: float = 0.0
    volume: float | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True, eq=False)
class QuoteUpdatedEvent(DomainEvent):
    """Raised when quote data is updated in cache.

    ``symbol`` is composite ``{code}:{exchange}``.
    """

    symbol: str = ""
    last_price: float = 0.0
    change: float | None = None
    change_percent: float | None = None
