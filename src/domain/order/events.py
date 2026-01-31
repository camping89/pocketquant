"""Order domain events."""

from dataclasses import dataclass

from src.domain.order.value_objects import OrderSide
from src.domain.shared.events import DomainEvent


@dataclass(frozen=True)
class OrderSubmitted(DomainEvent):
    """Event raised when an order is submitted to broker."""

    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float | None = None


@dataclass(frozen=True)
class OrderFilled(DomainEvent):
    """Event raised when an order is fully filled."""

    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: OrderSide = OrderSide.BUY
    filled_quantity: float = 0.0
    filled_price: float = 0.0


@dataclass(frozen=True)
class OrderPartiallyFilled(DomainEvent):
    """Event raised when an order is partially filled."""

    order_id: str = ""
    strategy_id: str = ""
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    remaining_quantity: float = 0.0


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    """Event raised when an order is cancelled."""

    order_id: str = ""
    strategy_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class OrderRejected(DomainEvent):
    """Event raised when an order is rejected by broker."""

    order_id: str = ""
    strategy_id: str = ""
    reason: str = ""
