"""Broker DTOs - data transfer objects for broker communication."""

from dataclasses import dataclass
from datetime import datetime

from src.domain.order import OrderStatus


@dataclass
class OrderResult:
    """Result of an order submission to broker."""

    order_id: str
    broker_order_id: str
    status: OrderStatus
    filled_quantity: float = 0.0
    filled_price: float | None = None
    error_message: str | None = None
    submitted_at: datetime | None = None

    @property
    def is_success(self) -> bool:
        """Check if order was accepted by broker."""
        return self.status not in (OrderStatus.REJECTED,)

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.status == OrderStatus.FILLED


@dataclass
class AccountBalance:
    """Account balance from broker."""

    total_equity: float
    available_balance: float
    currency: str = "USDT"
    margin_used: float = 0.0
    unrealized_pnl: float = 0.0

    @property
    def buying_power(self) -> float:
        """Available buying power (considers margin)."""
        return self.available_balance
