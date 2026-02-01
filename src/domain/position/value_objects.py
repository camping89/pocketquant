"""Position value objects - PnL and PositionSide."""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class PositionSide(Enum):
    """Position direction."""

    LONG = "long"
    SHORT = "short"


class PnL(BaseModel):
    """Profit and Loss calculation result."""

    model_config = ConfigDict(frozen=True)

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
