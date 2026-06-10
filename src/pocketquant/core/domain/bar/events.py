"""Bar domain events."""

from dataclasses import dataclass
from datetime import datetime

from pocketquant.core.domain.shared.events import DomainEvent


@dataclass(frozen=True, eq=False)
class BarCompletedEvent(DomainEvent):
    """Raised when a real-time bar is completed.

    ``symbol`` is composite ``{code}:{exchange}``.
    """

    symbol: str = ""
    interval: str = ""
    bar_start: datetime | None = None
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    tick_count: int = 0
