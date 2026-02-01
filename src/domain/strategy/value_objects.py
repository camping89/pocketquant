"""Strategy value objects - Signal and Direction."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class Direction(Enum):
    """Trading direction for signals."""

    LONG = "long"
    SHORT = "short"
    EXIT = "exit"
    FLAT = "flat"


class Signal(BaseModel):
    """Immutable trading signal from a strategy.

    Represents a trade intention before risk validation and sizing.
    """

    model_config = ConfigDict(frozen=True)

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

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {v}")
        return v

    @property
    def is_entry(self) -> bool:
        """Check if signal is an entry (long or short)."""
        return self.direction in (Direction.LONG, Direction.SHORT)

    @property
    def is_exit(self) -> bool:
        """Check if signal is an exit."""
        return self.direction == Direction.EXIT
