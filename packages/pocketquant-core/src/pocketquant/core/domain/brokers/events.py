"""Broker-level lifecycle event VO + callback type.

`OrderEvent` is a value object recording a single order status transition,
delivered alongside ``OrderResult`` via a dedicated callback channel.

Lives in core so both ``PaperBroker`` (emitter) and the backtest result
collector (consumer) can import it without crossing a dependency boundary.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pocketquant.core.domain.order.enums import OrderStatus

# Reason codes — string constants kept here for single source of truth.
REASON_SUBMIT = "submit"
REASON_MARKET_FILL = "market_fill"
REASON_LIMIT_CROSS = "limit_cross"
REASON_LIMIT_IMMEDIATE = "limit_immediate"
REASON_AUTO_SL = "auto_sl"
REASON_AUTO_TP = "auto_tp"
REASON_USER_CANCEL = "user_cancel"
REASON_END_OF_RUN = "end_of_run"
REASON_INSUFFICIENT_BALANCE = "insufficient_balance"
REASON_INVALID_LIMIT_PRICE = "invalid_limit_price"
REASON_NO_MARKET_PRICE = "no_market_price"


@dataclass
class OrderEvent:
    """Status transition record. Embedded in `backtest_orders.events[]`.

    ``from_status`` is None for the very first event (initial SUBMITTED record).
    """

    timestamp: datetime
    from_status: OrderStatus | None
    to_status: OrderStatus
    reason: str | None = None

    def to_mongo(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "from_status": self.from_status.value if self.from_status is not None else None,
            "to_status": self.to_status.value,
            "reason": self.reason,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> OrderEvent:
        from_raw = data.get("from_status")
        return cls(
            timestamp=data["timestamp"],
            from_status=OrderStatus(from_raw) if from_raw is not None else None,
            to_status=OrderStatus(data["to_status"]),
            reason=data.get("reason"),
        )


# Callback receives (order_id, event). Sync or async.
OrderEventCallback = Callable[[str, OrderEvent], None | Awaitable[None]]
