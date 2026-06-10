"""Order aggregate with state machine for order lifecycle — Pydantic model."""

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field, PrivateAttr

from pocketquant.core.common.time import utc_now
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.order.enums import OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.order.events import (
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderPartiallyFilledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
)
from pocketquant.core.domain.shared.events import DomainEvent


class InvalidOrderTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


class OrderAggregate(BaseModel):
    """Order aggregate root with state machine.

    ``symbol`` is composite ``{code}:{exchange}``.
    Tracks order lifecycle from creation to terminal state.
    """

    id: str
    subscription_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    sl_price: float | None = None
    tp_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: float | None = None
    broker_order_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    # State machine: valid transitions (class-level, allocated once)
    _VALID_TRANSITIONS: ClassVar[dict[OrderStatus, frozenset[OrderStatus]]] = {
        OrderStatus.PENDING: frozenset({OrderStatus.SUBMITTED, OrderStatus.REJECTED}),
        OrderStatus.SUBMITTED: frozenset(
            {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED}
        ),
        OrderStatus.PARTIALLY_FILLED: frozenset({OrderStatus.FILLED, OrderStatus.CANCELLED}),
    }

    @classmethod
    def create(
        cls,
        subscription_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        sl_price: float | None = None,
        tp_price: float | None = None,
    ) -> OrderAggregate:
        """Factory method to create a new order."""
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if order_type == OrderType.LIMIT and price is None:
            raise ValueError("Limit order requires price")
        if order_type in (OrderType.STOP_LIMIT, OrderType.STOP_MARKET) and stop_price is None:
            raise ValueError("Stop order requires stop_price")

        return cls(
            id=generate_id_str(),
            subscription_id=subscription_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            sl_price=sl_price,
            tp_price=tp_price,
        )

    def submit(self, broker_order_id: str) -> OrderAggregate:
        """Transition to SUBMITTED state."""
        self._validate_transition(OrderStatus.SUBMITTED)
        self.status = OrderStatus.SUBMITTED
        self.broker_order_id = broker_order_id
        self.updated_at = utc_now()
        self._events.append(
            OrderSubmittedEvent(
                order_id=self.id,
                subscription_id=self.subscription_id,
                symbol=self.symbol,
                side=self.side,
                quantity=self.quantity,
                price=self.price,
            )
        )
        return self

    def partial_fill(self, quantity: float, price: float) -> OrderAggregate:
        """Record a partial fill."""
        self._validate_transition(OrderStatus.PARTIALLY_FILLED)
        if quantity <= 0:
            raise ValueError("Fill quantity must be positive")
        if self.filled_quantity + quantity > self.quantity:
            raise ValueError("Fill quantity exceeds order quantity")

        total_filled = self.filled_quantity + quantity
        if self.filled_price is not None:
            self.filled_price = (
                self.filled_price * self.filled_quantity + price * quantity
            ) / total_filled
        else:
            self.filled_price = price

        self.filled_quantity = total_filled
        self.status = OrderStatus.PARTIALLY_FILLED
        self.updated_at = utc_now()
        self._events.append(
            OrderPartiallyFilledEvent(
                order_id=self.id,
                subscription_id=self.subscription_id,
                filled_quantity=quantity,
                filled_price=price,
                remaining_quantity=self.quantity - self.filled_quantity,
            )
        )
        return self

    def fill(self, quantity: float, price: float) -> OrderAggregate:
        """Fully fill the order."""
        if self.status == OrderStatus.PARTIALLY_FILLED:
            remaining = self.quantity - self.filled_quantity
            if quantity != remaining:
                raise ValueError(f"Fill quantity {quantity} != remaining {remaining}")
        else:
            self._validate_transition(OrderStatus.FILLED)
            if quantity != self.quantity:
                raise ValueError("Full fill quantity must match order quantity")

        if self.filled_price is not None and self.filled_quantity > 0:
            self.filled_price = (
                self.filled_price * self.filled_quantity + price * quantity
            ) / self.quantity
        else:
            self.filled_price = price

        self.filled_quantity = self.quantity
        self.status = OrderStatus.FILLED
        self.updated_at = utc_now()

        self._events.append(
            OrderFilledEvent(
                order_id=self.id,
                subscription_id=self.subscription_id,
                symbol=self.symbol,
                side=self.side,
                filled_quantity=self.quantity,
                filled_price=self.filled_price,
            )
        )
        return self

    def cancel(self, reason: str = "") -> OrderAggregate:
        """Cancel the order."""
        if self.status.is_terminal:
            raise InvalidOrderTransitionError(
                f"Cannot cancel order in terminal state: {self.status}"
            )
        self.status = OrderStatus.CANCELLED
        self.updated_at = utc_now()
        self._events.append(
            OrderCancelledEvent(
                order_id=self.id,
                subscription_id=self.subscription_id,
                reason=reason,
            )
        )
        return self

    def reject(self, reason: str) -> OrderAggregate:
        """Reject the order (broker rejection)."""
        self._validate_transition(OrderStatus.REJECTED)
        self.status = OrderStatus.REJECTED
        self.updated_at = utc_now()
        self._events.append(
            OrderRejectedEvent(
                order_id=self.id,
                subscription_id=self.subscription_id,
                reason=reason,
            )
        )
        return self

    def _validate_transition(self, target: OrderStatus) -> None:
        """Validate state transition is allowed."""
        allowed = self._VALID_TRANSITIONS.get(self.status, frozenset())
        if target not in allowed:
            raise InvalidOrderTransitionError(f"Cannot transition from {self.status} to {target}")

    def collect_events(self) -> list[DomainEvent]:
        """Collect and clear pending domain events."""
        events = self._events.copy()
        self._events.clear()
        return events

    @property
    def remaining_quantity(self) -> float:
        """Get unfilled quantity."""
        return self.quantity - self.filled_quantity

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document."""
        return {
            "_id": self.id,
            "subscription_id": self.subscription_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
            "status": self.status.value,
            "filled_quantity": self.filled_quantity,
            "filled_price": self.filled_price,
            "broker_order_id": self.broker_order_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> OrderAggregate:
        """Reconstruct from MongoDB document."""
        return cls(
            id=doc["_id"],
            subscription_id=doc["subscription_id"],
            symbol=doc["symbol"],
            side=OrderSide(doc["side"]),
            order_type=OrderType(doc["order_type"]),
            quantity=doc["quantity"],
            price=doc.get("price"),
            stop_price=doc.get("stop_price"),
            status=OrderStatus(doc["status"]),
            filled_quantity=doc.get("filled_quantity", 0.0),
            filled_price=doc.get("filled_price"),
            broker_order_id=doc.get("broker_order_id"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )
