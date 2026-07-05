from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr

from pocketquant.core.common.time import utc_now
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.position.enums import PositionSide
from pocketquant.core.domain.position.events import (
    PositionClosedEvent,
    PositionOpenedEvent,
    PositionUpdatedEvent,
    TradeClosedEvent,
)
from pocketquant.core.domain.position.value_objects import PnL
from pocketquant.core.domain.shared.events import DomainEvent


class PositionAggregate(BaseModel):
    """Position aggregate root tracking entry, quantity, and P&L.

    ``symbol`` is composite ``{code}:{exchange}``.
    Handles position lifecycle from open to close with proper
    average price calculation on adds and realized P&L on reduces.
    """

    id: UUID
    subscription_id: str
    symbol: str
    side: PositionSide
    entry_price: float
    quantity: float
    current_price: float
    realized_pnl: float = 0.0
    is_closed: bool = False
    opened_at: datetime = Field(default_factory=utc_now)
    closed_at: datetime | None = None
    # Risk levels captured on open; consumed by PaperBrokerAdapter auto-fill loop.
    sl_price: float | None = None
    tp_price: float | None = None
    entry_order_id: str | None = None
    # Accumulated entry-side commission; reduce/close drains a proportional portion.
    entry_commission: float = 0.0
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    @classmethod
    def open(
        cls,
        subscription_id: str,
        symbol: str,
        side: PositionSide,
        entry_price: float,
        quantity: float,
        sl_price: float | None = None,
        tp_price: float | None = None,
        entry_order_id: str | None = None,
        entry_commission: float = 0.0,
        opened_at: datetime | None = None,
    ) -> PositionAggregate:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if entry_price <= 0:
            raise ValueError("Entry price must be positive")

        position = cls(
            id=generate_id(),
            subscription_id=subscription_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            current_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            entry_order_id=entry_order_id,
            entry_commission=entry_commission,
        )
        # opened_at omitted → keep the field default_factory (utc_now) value.
        if opened_at is not None:
            position.opened_at = opened_at
        position._events.append(
            PositionOpenedEvent(
                position_id=str(position.id),
                subscription_id=subscription_id,
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                quantity=quantity,
            )
        )
        return position

    def update_price(self, current_price: float) -> PositionAggregate:
        if current_price <= 0:
            raise ValueError("Price must be positive")
        self.current_price = current_price
        return self

    def add_quantity(
        self, quantity: float, price: float, commission: float = 0.0
    ) -> PositionAggregate:
        if self.is_closed:
            raise ValueError("Cannot add to closed position")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if price <= 0:
            raise ValueError("Price must be positive")

        total_cost = self.entry_price * self.quantity + price * quantity
        self.quantity += quantity
        self.entry_price = total_cost / self.quantity
        self.current_price = price
        self.entry_commission += commission

        self._events.append(
            PositionUpdatedEvent(
                position_id=str(self.id),
                subscription_id=self.subscription_id,
                quantity=self.quantity,
                average_price=self.entry_price,
                unrealized_pnl=self.unrealized_pnl,
            )
        )
        return self

    def reduce_quantity(
        self,
        quantity: float,
        price: float,
        exit_commission: float = 0.0,
        exit_order_id: str | None = None,
        exit_time: datetime | None = None,
    ) -> PositionAggregate:
        if self.is_closed:
            raise ValueError("Cannot reduce closed position")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if quantity > self.quantity:
            raise ValueError(f"Cannot reduce by {quantity}, only {self.quantity} held")

        qty_before = self.quantity
        entry_comm_before = self.entry_commission
        entry_time = self.opened_at
        entry_price_snap = self.entry_price
        direction = self.side.name

        pnl_per_unit = self._calculate_pnl_per_unit(price)
        realized = pnl_per_unit * quantity
        self.realized_pnl += realized
        self.quantity -= quantity
        self.current_price = price

        entry_commission_portion = (
            entry_comm_before * quantity / qty_before if qty_before > 0 else 0.0
        )
        self.entry_commission -= entry_commission_portion
        xt = exit_time or utc_now()

        self._events.append(
            TradeClosedEvent(
                position_id=str(self.id),
                subscription_id=self.subscription_id,
                symbol=self.symbol,
                direction=direction,
                entry_order_id=self.entry_order_id,
                entry_price=entry_price_snap,
                entry_time=entry_time,
                quantity=quantity,
                exit_order_id=exit_order_id,
                exit_price=price,
                exit_time=xt,
                sl_price=self.sl_price,
                tp_price=self.tp_price,
                pnl=realized,
                commission=entry_commission_portion + exit_commission,
                duration_seconds=(xt - entry_time).total_seconds(),
            )
        )

        if self.quantity == 0:
            return self._close(price)

        self._events.append(
            PositionUpdatedEvent(
                position_id=str(self.id),
                subscription_id=self.subscription_id,
                quantity=self.quantity,
                average_price=self.entry_price,
                unrealized_pnl=self.unrealized_pnl,
            )
        )
        return self

    def close(self, exit_price: float) -> PositionAggregate:
        if self.is_closed:
            raise ValueError("Position already closed")
        return self.reduce_quantity(self.quantity, exit_price)

    def _close(self, exit_price: float) -> PositionAggregate:
        self.is_closed = True
        self.closed_at = utc_now()
        self._events.append(
            PositionClosedEvent(
                position_id=str(self.id),
                subscription_id=self.subscription_id,
                symbol=self.symbol,
                side=self.side,
                entry_price=self.entry_price,
                exit_price=exit_price,
                quantity=0,  # Already reduced
                realized_pnl=self.realized_pnl,
            )
        )
        return self

    def _calculate_pnl_per_unit(self, current_price: float) -> float:
        if self.side == PositionSide.LONG:
            return current_price - self.entry_price
        else:  # SHORT
            return self.entry_price - current_price

    @property
    def unrealized_pnl(self) -> float:
        if self.is_closed:
            return 0.0
        return self._calculate_pnl_per_unit(self.current_price) * self.quantity

    @property
    def pnl(self) -> PnL:
        return PnL(unrealized=self.unrealized_pnl, realized=self.realized_pnl)

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.entry_price

    def collect_events(self) -> list[DomainEvent]:
        events = self._events.copy()
        self._events.clear()
        return events

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document."""
        return {
            "_id": str(self.id),
            "subscription_id": self.subscription_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "current_price": self.current_price,
            "realized_pnl": self.realized_pnl,
            "is_closed": self.is_closed,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "sl_price": self.sl_price,
            "tp_price": self.tp_price,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> PositionAggregate:
        """Reconstruct from MongoDB document."""
        return cls(
            id=doc["_id"],
            subscription_id=doc["subscription_id"],
            symbol=doc["symbol"],
            side=PositionSide(doc["side"]),
            entry_price=doc["entry_price"],
            quantity=doc["quantity"],
            current_price=doc["current_price"],
            realized_pnl=doc.get("realized_pnl", 0.0),
            is_closed=doc.get("is_closed", False),
            opened_at=doc["opened_at"],
            closed_at=doc.get("closed_at"),
            sl_price=doc.get("sl_price"),
            tp_price=doc.get("tp_price"),
        )
