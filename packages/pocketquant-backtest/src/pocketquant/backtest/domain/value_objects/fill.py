"""Fill VO — atomic execution event. One order may emit multiple Fills (partials)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pocketquant.core.domain.order.enums import OrderSide


@dataclass
class Fill:
    """Atomic execution event (Backtrader/QC convention).

    Embedded in `Order.fills[]`. `order_id` is redundant when embedded but kept
    so a standalone Fill carries its parent reference.
    """

    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    slippage: float
    timestamp: datetime

    def to_mongo(self, *, embed: bool = False) -> dict[str, Any]:
        """Serialize. When embedded in an Order doc, drop redundant order_id."""
        doc: dict[str, Any] = {
            "fill_id": self.fill_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "commission": self.commission,
            "slippage": self.slippage,
            "timestamp": self.timestamp,
        }
        if not embed:
            doc["order_id"] = self.order_id
        return doc

    @classmethod
    def from_mongo(cls, data: dict[str, Any], *, order_id: str | None = None) -> Fill:
        """Deserialize. Caller passes parent order_id when reading an embedded fill."""
        resolved_order_id = data.get("order_id") or order_id
        if not resolved_order_id:
            raise ValueError(
                "Fill must have order_id (present in doc or passed as kwarg for embedded fills)"
            )
        return cls(
            fill_id=data["fill_id"],
            order_id=resolved_order_id,
            symbol=data["symbol"],
            side=OrderSide(data["side"]),
            quantity=data["quantity"],
            price=data["price"],
            commission=data.get("commission", 0.0),
            slippage=data.get("slippage", 0.0),
            timestamp=data["timestamp"],
        )
