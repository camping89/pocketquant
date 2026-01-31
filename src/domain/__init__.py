"""Domain layer - Pure business logic with zero I/O imports."""

from src.domain.shared.domain_event import DomainEvent
from src.domain.shared.value_objects import Interval, Symbol

# Strategy domain
from src.domain.strategy import Direction, Signal, SignalGeneratedEvent

# Order domain
from src.domain.order import (
    InvalidOrderTransitionError,
    OrderAggregate,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderPartiallyFilledEvent,
    OrderRejectedEvent,
    OrderSide,
    OrderStatus,
    OrderSubmittedEvent,
    OrderType,
)

# Position domain
from src.domain.position import (
    PnL,
    PositionAggregate,
    PositionClosedEvent,
    PositionOpenedEvent,
    PositionSide,
    PositionUpdatedEvent,
)

# Risk domain
from src.domain.risk import PositionSizer, RiskConfig, RiskModel

__all__ = [
    # Shared
    "DomainEvent",
    "Interval",
    "Symbol",
    # Strategy
    "Direction",
    "Signal",
    "SignalGeneratedEvent",
    # Order
    "InvalidOrderTransitionError",
    "OrderAggregate",
    "OrderCancelledEvent",
    "OrderFilledEvent",
    "OrderPartiallyFilledEvent",
    "OrderRejectedEvent",
    "OrderSide",
    "OrderStatus",
    "OrderSubmittedEvent",
    "OrderType",
    # Position
    "PnL",
    "PositionAggregate",
    "PositionClosedEvent",
    "PositionOpenedEvent",
    "PositionSide",
    "PositionUpdatedEvent",
    # Risk
    "PositionSizer",
    "RiskConfig",
    "RiskModel",
]
