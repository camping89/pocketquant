"""Domain layer - Pure business logic with zero I/O imports."""

# Bar domain (collection-backed)
from src.domain.bar import Bar, BarCompletedEvent

# Order domain (collection-backed)
from src.domain.order import (
    InvalidOrderTransitionError,
    OrderAggregate,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderPartiallyFilledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
)
from src.domain.order.enums import OrderSide, OrderStatus, OrderType

# Position domain (collection-backed)
from src.domain.position import (
    PositionAggregate,
    PositionClosedEvent,
    PositionOpenedEvent,
    PositionUpdatedEvent,
)
from src.domain.position.enums import PositionSide
from src.domain.position.value_objects import PnL

# Sync status domain (collection-backed)
from src.domain.sync_status import SyncStatus

# Backtest domain (collection-backed)
from src.domain.backtest import BacktestResult, OptimizationResult

# Concepts - Risk
from src.domain.concepts.risk import PositionSizer, RiskConfig
from src.domain.concepts.risk.enums import RiskModel

# Concepts - Strategy
from src.domain.concepts.strategy import SignalGeneratedEvent
from src.domain.concepts.strategy.enums import Direction
from src.domain.concepts.strategy.value_objects import Signal

# Symbol domain (collection-backed)
from src.domain.symbol import Symbol

# Shared
from src.domain.shared.events import DomainEvent
from src.domain.shared.enums import Interval

__all__ = [
    # Shared
    "DomainEvent",
    "Interval",
    "Symbol",
    # Bar
    "Bar",
    "BarCompletedEvent",
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
    # Sync status
    "SyncStatus",
    # Backtest
    "BacktestResult",
    "OptimizationResult",
    # Risk
    "PositionSizer",
    "RiskConfig",
    "RiskModel",
    # Strategy
    "Direction",
    "Signal",
    "SignalGeneratedEvent",
]
