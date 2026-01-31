"""Domain layer - Pure business logic with zero I/O imports."""

from src.domain.shared.events import DomainEvent
from src.domain.shared.value_objects import Interval, Symbol

# Strategy domain
from src.domain.strategy import Direction, Signal, SignalGenerated

# Order domain
from src.domain.order import (
    InvalidOrderTransitionError,
    OrderAggregate,
    OrderCancelled,
    OrderFilled,
    OrderPartiallyFilled,
    OrderRejected,
    OrderSide,
    OrderStatus,
    OrderSubmitted,
    OrderType,
)

# Position domain
from src.domain.position import (
    PnL,
    PositionAggregate,
    PositionClosed,
    PositionOpened,
    PositionSide,
    PositionUpdated,
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
    "SignalGenerated",
    # Order
    "InvalidOrderTransitionError",
    "OrderAggregate",
    "OrderCancelled",
    "OrderFilled",
    "OrderPartiallyFilled",
    "OrderRejected",
    "OrderSide",
    "OrderStatus",
    "OrderSubmitted",
    "OrderType",
    # Position
    "PnL",
    "PositionAggregate",
    "PositionClosed",
    "PositionOpened",
    "PositionSide",
    "PositionUpdated",
    # Risk
    "PositionSizer",
    "RiskConfig",
    "RiskModel",
]
