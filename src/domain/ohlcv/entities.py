"""OHLCV entities."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from src.domain.ohlcv.value_objects import OHLCV, BarRange
from src.domain.shared.value_objects import Interval, Symbol


@dataclass(eq=False)
class Bar:
    """Entity representing a price bar with identity."""

    id: UUID = field(default_factory=uuid4)
    symbol: Symbol | None = None
    interval: Interval | None = None
    time_range: BarRange | None = None
    ohlcv: OHLCV | None = None
    tick_count: int = 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Bar):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def is_complete(self) -> bool:
        return self.ohlcv is not None and self.tick_count > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "symbol": str(self.symbol) if self.symbol else None,
            "interval": self.interval.value if self.interval else None,
            "bar_start": self.time_range.start.isoformat() if self.time_range else None,
            "bar_end": self.time_range.end.isoformat() if self.time_range else None,
            "open": self.ohlcv.open if self.ohlcv else None,
            "high": self.ohlcv.high if self.ohlcv else None,
            "low": self.ohlcv.low if self.ohlcv else None,
            "close": self.ohlcv.close if self.ohlcv else None,
            "volume": self.ohlcv.volume if self.ohlcv else None,
            "tick_count": self.tick_count,
        }
