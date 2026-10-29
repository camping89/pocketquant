from dataclasses import dataclass
from datetime import datetime

from pocketquant.core.domain.shared.events import DomainEvent


@dataclass(frozen=True, eq=False)
class BarCompletedEvent(DomainEvent):
    """Raised when a real-time bar is completed.

    ``symbol`` is composite ``{code}:{exchange}``. ``bar_end`` is None for replayed
    (backtest) bars; ``closed_by`` is ``tick`` or ``timer``.
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
    bar_end: datetime | None = None
    gap: bool = False
    closed_at: datetime | None = None
    closing_tick_at: datetime | None = None
    closed_by: str = "tick"
