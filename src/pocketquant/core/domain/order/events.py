from dataclasses import dataclass

from pocketquant.core.domain.order.enums import OrderSide
from pocketquant.core.domain.shared.events import DomainEvent


@dataclass(frozen=True, eq=False)
class OrderSubmittedEvent(DomainEvent):
    order_id: str = ""
    subscription_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float | None = None


# An entry fill carries the order's SL and TP so the position mirror stores them; exit
# fills leave them None.
@dataclass(frozen=True, eq=False)
class OrderFilledEvent(DomainEvent):
    order_id: str = ""
    subscription_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    sl_price: float | None = None
    tp_price: float | None = None


@dataclass(frozen=True, eq=False)
class OrderPartiallyFilledEvent(DomainEvent):
    order_id: str = ""
    subscription_id: str = ""
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    remaining_quantity: float = 0.0


@dataclass(frozen=True, eq=False)
class OrderCancelledEvent(DomainEvent):
    order_id: str = ""
    subscription_id: str = ""
    reason: str = ""


@dataclass(frozen=True, eq=False)
class OrderRejectedEvent(DomainEvent):
    order_id: str = ""
    subscription_id: str = ""
    reason: str = ""
