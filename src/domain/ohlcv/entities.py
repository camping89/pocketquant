"""OHLCV entities."""

from dataclasses import dataclass, field
from datetime import datetime

from src.common.uuid import UUID, generate_id
from src.domain.shared.value_objects import Interval


@dataclass(eq=False)
class Bar:
    """Entity representing a stored OHLCV price bar with identity.

    Flat structure for direct field access. Used by repositories,
    handlers, and backtesting engine.
    """

    id: UUID = field(default_factory=generate_id)
    symbol: str = ""
    exchange: str = ""
    interval: Interval | None = None
    datetime: datetime | None = None
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    tick_count: int = 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Bar):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def is_complete(self) -> bool:
        return self.tick_count > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval.value if self.interval else None,
            "datetime": self.datetime.isoformat() if self.datetime else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
        }


@dataclass
class SyncStatus:
    """Entity tracking data sync status for a symbol/exchange/interval."""

    symbol: str = ""
    exchange: str = ""
    interval: str = ""
    status: str = "pending"
    last_sync_at: datetime | None = None
    last_bar_at: datetime | None = None
    bar_count: int = 0
    error_message: str | None = None
