from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


# entry_order_id is nullable for migrated docs whose order id could not be rebuilt.
# entry_commission_portion is commission scaled by qty_remaining / qty_original.
@dataclass
class OpenLot:
    symbol: str
    direction: str  # "LONG" | "SHORT"
    entry_price: float
    entry_time: datetime
    quantity: float
    sl_price: float | None
    tp_price: float | None
    entry_order_id: str | None
    entry_commission_portion: float

    def to_mongo(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "quantity": self.quantity,
            "sl_price": self.sl_price,
            "tp_price": self.tp_price,
            "entry_order_id": self.entry_order_id,
            "entry_commission_portion": self.entry_commission_portion,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> OpenLot:
        return cls(
            symbol=data["symbol"],
            direction=data.get("direction", "LONG"),
            entry_price=data["entry_price"],
            entry_time=data["entry_time"],
            quantity=data["quantity"],
            sl_price=data.get("sl_price"),
            tp_price=data.get("tp_price"),
            entry_order_id=data.get("entry_order_id"),
            entry_commission_portion=data.get("entry_commission_portion", 0.0),
        )
