"""Order domain events."""

from src.domain.order.value_objects import OrderSide
from src.domain.shared.domain_event import DomainEvent


class OrderSubmittedEvent(DomainEvent):
    """Event raised when an order is submitted to broker."""

    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float | None = None


class OrderFilledEvent(DomainEvent):
    """Event raised when an order is fully filled."""

    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: OrderSide = OrderSide.BUY
    filled_quantity: float = 0.0
    filled_price: float = 0.0


class OrderPartiallyFilledEvent(DomainEvent):
    """Event raised when an order is partially filled."""

    order_id: str = ""
    strategy_id: str = ""
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    remaining_quantity: float = 0.0


class OrderCancelledEvent(DomainEvent):
    """Event raised when an order is cancelled."""

    order_id: str = ""
    strategy_id: str = ""
    reason: str = ""


class OrderRejectedEvent(DomainEvent):
    """Event raised when an order is rejected by broker."""

    order_id: str = ""
    strategy_id: str = ""
    reason: str = ""
