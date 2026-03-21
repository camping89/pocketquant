"""Position aggregate for tracking open positions and P&L — Pydantic model."""

from datetime import UTC, datetime
from typing import Any

from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.position.enums import PositionSide
from pocketquant.core.domain.position.events import (
    PositionClosedEvent,
    PositionOpenedEvent,
    PositionUpdatedEvent,
)
from pocketquant.core.domain.position.value_objects import PnL
from pocketquant.core.domain.shared.events import DomainEvent
from pydantic import BaseModel, Field, PrivateAttr


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PositionAggregate(BaseModel):
    """Position aggregate root tracking entry, quantity, and P&L.

    Handles position lifecycle from open to close with proper
    average price calculation on adds and realized P&L on reduces.
    """

    id: str
    strategy_id: str
    symbol: str
    exchange: str
    side: PositionSide
    entry_price: float
    quantity: float
    current_price: float
    realized_pnl: float = 0.0
    is_closed: bool = False
    opened_at: datetime = Field(default_factory=_utc_now)
    closed_at: datetime | None = None
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    @classmethod
    def open(
        cls,
        strategy_id: str,
        symbol: str,
        exchange: str,
        side: PositionSide,
        entry_price: float,
        quantity: float,
    ) -> PositionAggregate:
        """Factory method to open a new position."""
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if entry_price <= 0:
            raise ValueError("Entry price must be positive")

        position = cls(
            id=generate_id_str(),
            strategy_id=strategy_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            current_price=entry_price,
        )
        position._events.append(
            PositionOpenedEvent(
                position_id=position.id,
                strategy_id=strategy_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                entry_price=entry_price,
                quantity=quantity,
            )
        )
        return position

    def update_price(self, current_price: float) -> PositionAggregate:
        """Update current market price for P&L calculation."""
        if current_price <= 0:
            raise ValueError("Price must be positive")
        self.current_price = current_price
        return self

    def add_quantity(self, quantity: float, price: float) -> PositionAggregate:
        """Add to position (scale in) with weighted average price."""
        if self.is_closed:
            raise ValueError("Cannot add to closed position")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if price <= 0:
            raise ValueError("Price must be positive")

        # Calculate weighted average entry price
        total_cost = self.entry_price * self.quantity + price * quantity
        self.quantity += quantity
        self.entry_price = total_cost / self.quantity
        self.current_price = price

        self._events.append(
            PositionUpdatedEvent(
                position_id=self.id,
                strategy_id=self.strategy_id,
                quantity=self.quantity,
                average_price=self.entry_price,
                unrealized_pnl=self.unrealized_pnl,
            )
        )
        return self

    def reduce_quantity(self, quantity: float, price: float) -> PositionAggregate:
        """Reduce position (scale out) and realize P&L."""
        if self.is_closed:
            raise ValueError("Cannot reduce closed position")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if quantity > self.quantity:
            raise ValueError(f"Cannot reduce by {quantity}, only {self.quantity} held")

        # Calculate realized P&L for this reduction
        pnl_per_unit = self._calculate_pnl_per_unit(price)
        realized = pnl_per_unit * quantity
        self.realized_pnl += realized
        self.quantity -= quantity
        self.current_price = price

        if self.quantity == 0:
            return self._close(price)

        self._events.append(
            PositionUpdatedEvent(
                position_id=self.id,
                strategy_id=self.strategy_id,
                quantity=self.quantity,
                average_price=self.entry_price,
                unrealized_pnl=self.unrealized_pnl,
            )
        )
        return self

    def close(self, exit_price: float) -> PositionAggregate:
        """Fully close the position at exit price."""
        if self.is_closed:
            raise ValueError("Position already closed")
        return self.reduce_quantity(self.quantity, exit_price)

    def _close(self, exit_price: float) -> PositionAggregate:
        """Internal close after reducing to zero."""
        self.is_closed = True
        self.closed_at = datetime.now(UTC)
        self._events.append(
            PositionClosedEvent(
                position_id=self.id,
                strategy_id=self.strategy_id,
                symbol=self.symbol,
                exchange=self.exchange,
                side=self.side,
                entry_price=self.entry_price,
                exit_price=exit_price,
                quantity=0,  # Already reduced
                realized_pnl=self.realized_pnl,
            )
        )
        return self

    def _calculate_pnl_per_unit(self, current_price: float) -> float:
        """Calculate P&L per unit based on position side."""
        if self.side == PositionSide.LONG:
            return current_price - self.entry_price
        else:  # SHORT
            return self.entry_price - current_price

    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L at current price."""
        if self.is_closed:
            return 0.0
        return self._calculate_pnl_per_unit(self.current_price) * self.quantity

    @property
    def pnl(self) -> PnL:
        """Get full P&L breakdown."""
        return PnL(unrealized=self.unrealized_pnl, realized=self.realized_pnl)

    @property
    def market_value(self) -> float:
        """Current market value of the position."""
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        """Total cost basis of the position."""
        return self.quantity * self.entry_price

    def collect_events(self) -> list[DomainEvent]:
        """Collect and clear pending domain events."""
        events = self._events.copy()
        self._events.clear()
        return events

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document."""
        return {
            "_id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "current_price": self.current_price,
            "realized_pnl": self.realized_pnl,
            "is_closed": self.is_closed,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> PositionAggregate:
        """Reconstruct from MongoDB document."""
        return cls(
            id=doc["_id"],
            strategy_id=doc["strategy_id"],
            symbol=doc["symbol"],
            exchange=doc["exchange"],
            side=PositionSide(doc["side"]),
            entry_price=doc["entry_price"],
            quantity=doc["quantity"],
            current_price=doc["current_price"],
            realized_pnl=doc.get("realized_pnl", 0.0),
            is_closed=doc.get("is_closed", False),
            opened_at=doc["opened_at"],
            closed_at=doc.get("closed_at"),
        )
