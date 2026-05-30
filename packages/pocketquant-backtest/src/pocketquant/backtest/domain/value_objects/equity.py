from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class EquityPoint:
    """Single point on the equity curve (recorded on position changes only)."""

    timestamp: datetime
    equity: float
    drawdown: float  # Current drawdown from peak (negative value)

    def to_mongo(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "equity": self.equity,
            "drawdown": self.drawdown,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> EquityPoint:
        return cls(
            timestamp=data["timestamp"],
            equity=data["equity"],
            drawdown=data.get("drawdown", 0.0),
        )
