"""Order enums - order types, sides, and status."""

from enum import Enum


class OrderType(Enum):
    """Order execution type."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_LIMIT = "stop_limit"
    STOP_MARKET = "stop_market"


class OrderSide(Enum):
    """Order direction."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order lifecycle status.

    State machine:
    PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED
                       → CANCELLED
           → REJECTED
    """

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    @property
    def is_terminal(self) -> bool:
        """Check if status is terminal (no further transitions)."""
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        )

    @property
    def is_active(self) -> bool:
        """Check if order is still active in the market."""
        return self in (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)
