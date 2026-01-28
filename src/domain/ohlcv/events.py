"""OHLCV domain events."""

from dataclasses import dataclass
from datetime import datetime

from src.domain.shared.events import DomainEvent


@dataclass(frozen=True)
class HistoricalDataSynced(DomainEvent):
    """Raised when historical OHLCV data is synchronized from provider."""

    symbol: str = ""
    exchange: str = ""
    interval: str = ""
    bars_count: int = 0
    first_bar_at: datetime | None = None
    last_bar_at: datetime | None = None


@dataclass(frozen=True)
class BarCompleted(DomainEvent):
    """Raised when a real-time bar is completed."""

    symbol: str = ""
    exchange: str = ""
    interval: str = ""
    bar_start: datetime | None = None
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    tick_count: int = 0
