"""Position value objects - PnL and PositionSide."""

from dataclasses import dataclass
from enum import Enum


class PositionSide(Enum):
    """Position direction."""

    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class PnL:
    """Profit and Loss calculation result."""

    unrealized: float
    realized: float

    @property
    def total(self) -> float:
        """Total P&L (unrealized + realized)."""
        return self.unrealized + self.realized

    @property
    def is_profitable(self) -> bool:
        """Check if position is profitable."""
        return self.total > 0
