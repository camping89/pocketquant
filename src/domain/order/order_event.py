"""Order domain events."""

from dataclasses import dataclass

from src.domain.order.value_objects import OrderSide
from src.domain.shared.domain_event import DomainEvent


@dataclass(frozen=True, eq=False)
class OrderSubmittedEvent(DomainEvent):
    """Event raised when an order is submitted to broker."""

    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float | None = None


@dataclass(frozen=True, eq=False)
class OrderFilledEvent(DomainEvent):
    """Event raised when an order is fully filled."""

    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: OrderSide = OrderSide.BUY
    filled_quantity: float = 0.0
    filled_price: float = 0.0


@dataclass(frozen=True, eq=False)
class OrderPartiallyFilledEvent(DomainEvent):
    """Event raised when an order is partially filled."""

    order_id: str = ""
    strategy_id: str = ""
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    remaining_quantity: float = 0.0


@dataclass(frozen=True, eq=False)
class OrderCancelledEvent(DomainEvent):
    """Event raised when an order is cancelled."""

    order_id: str = ""
    strategy_id: str = ""
    reason: str = ""


@dataclass(frozen=True, eq=False)
class OrderRejectedEvent(DomainEvent):
    """Event raised when an order is rejected by broker."""

    order_id: str = ""
    strategy_id: str = ""
    reason: str = ""
