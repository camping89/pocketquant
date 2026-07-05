from dataclasses import dataclass
from datetime import datetime

from pocketquant.core.domain.order import OrderSide, OrderStatus


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
    sl_price: float | None = None
    tp_price: float | None = None
    side: OrderSide | None = (
        None  # BUY/SELL — used by FIFO lot tracker; optional for backward compat
    )
    commission: float = 0.0  # cost per fill (paper: computed; OKX: abs(venue fee)); 0 for non-fills

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
    total_equity: float
    available_balance: float
    currency: str = "USDT"
    margin_used: float = 0.0
    unrealized_pnl: float = 0.0

    @property
    def buying_power(self) -> float:
        return self.available_balance
