"""Position document model for MongoDB."""

from datetime import datetime
from pydantic import BaseModel, Field

from src.domain.position import PositionAggregate, PositionSide


class PositionDocument(BaseModel):
    """MongoDB document for position persistence."""

    id: str = Field(alias="_id")
    strategy_id: str
    symbol: str
    exchange: str
    side: str
    entry_price: float
    quantity: float
    current_price: float
    realized_pnl: float = 0.0
    is_closed: bool = False
    opened_at: datetime
    closed_at: datetime | None = None

    model_config = {"populate_by_name": True}

    @classmethod
    def from_aggregate(cls, pos: PositionAggregate) -> "PositionDocument":
        return cls(
            _id=pos.id,
            strategy_id=pos.strategy_id,
            symbol=pos.symbol,
            exchange=pos.exchange,
            side=pos.side.value,
            entry_price=pos.entry_price,
            quantity=pos.quantity,
            current_price=pos.current_price,
            realized_pnl=pos.realized_pnl,
            is_closed=pos.is_closed,
            opened_at=pos.opened_at,
            closed_at=pos.closed_at,
        )

    def to_aggregate(self) -> PositionAggregate:
        return PositionAggregate(
            id=self.id,
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            exchange=self.exchange,
            side=PositionSide(self.side),
            entry_price=self.entry_price,
            quantity=self.quantity,
            current_price=self.current_price,
            realized_pnl=self.realized_pnl,
            is_closed=self.is_closed,
            opened_at=self.opened_at,
            closed_at=self.closed_at,
        )
