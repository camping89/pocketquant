from dataclasses import dataclass
from datetime import datetime

from pocketquant.core.domain.order import OrderSide, OrderStatus


@dataclass
class OrderResult:
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
    # Cost per fill (paper: computed; Exness: abs(deal commission)); 0 for non-fills.
    commission: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status not in (OrderStatus.REJECTED,)

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED


@dataclass
class AccountBalance:
    total_equity: float
    available_balance: float
    currency: str = "USDT"
    margin_used: float = 0.0
    unrealized_pnl: float = 0.0
