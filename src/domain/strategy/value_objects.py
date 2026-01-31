"""Strategy value objects - Signal and Direction."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Direction(Enum):
    """Trading direction for signals."""

    LONG = "long"
    SHORT = "short"
    EXIT = "exit"
    FLAT = "flat"


@dataclass(frozen=True)
class Signal:
    """Immutable trading signal from a strategy.

    Represents a trade intention before risk validation and sizing.
    """

    symbol: str
    exchange: str
    direction: Direction
    confidence: float  # 0.0 - 1.0
    timestamp: datetime
    strategy_id: str
    entry_price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    entry_logic: str = ""

    def __post_init__(self) -> None:
        """Validate signal fields."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")

    @property
    def is_entry(self) -> bool:
        """Check if signal is an entry (long or short)."""
        return self.direction in (Direction.LONG, Direction.SHORT)

    @property
    def is_exit(self) -> bool:
        """Check if signal is an exit."""
        return self.direction == Direction.EXIT
