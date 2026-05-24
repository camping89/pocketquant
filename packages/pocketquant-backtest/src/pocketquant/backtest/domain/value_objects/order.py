"""Order VO — order intent with full lifecycle (persisted in `backtest_orders`).

``OrderEvent`` is defined in `pocketquant.core.infrastructure.brokers.events`
so PaperBroker (emitter) and the backtest collector (consumer) can both import
it without crossing the core → backtest dependency boundary. Re-exported here
for ergonomic ``from pocketquant.backtest.domain import OrderEvent`` usage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pocketquant.core.domain.order.enums import OrderSide, OrderStatus, OrderType
from pocketquant.core.infrastructure.brokers.events import OrderEvent

from pocketquant.backtest.domain.value_objects.fill import Fill

__all__ = ["Order", "OrderEvent"]


@dataclass
class Order:
    """Order intent with full lifecycle (Backtrader/QC convention).

    Persisted standalone in `backtest_orders` with `events[]` + `fills[]` embedded.
    Side / type / status typed as core enums (not bare strings) for safety.
    """

    order_id: str
    run_id: str
    strategy_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None  # required for LIMIT/STOP
    sl_price: float | None
    tp_price: float | None
    status: OrderStatus
    submitted_at: datetime
    last_updated_at: datetime
    events: list[OrderEvent] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    resulting_trade_id: str | None = None

    def to_mongo(self) -> dict[str, Any]:
        return {
            "_id": self.order_id,
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "sl_price": self.sl_price,
            "tp_price": self.tp_price,
            "status": self.status.value,
            "submitted_at": self.submitted_at,
            "last_updated_at": self.last_updated_at,
            "events": [e.to_mongo() for e in self.events],
            "fills": [f.to_mongo(embed=True) for f in self.fills],
            "resulting_trade_id": self.resulting_trade_id,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> Order:
        order_id = data["_id"]
        return cls(
            order_id=order_id,
            run_id=data["run_id"],
            strategy_id=data["strategy_id"],
            symbol=data["symbol"],
            side=OrderSide(data["side"]),
            order_type=OrderType(data["order_type"]),
            quantity=data["quantity"],
            price=data.get("price"),
            sl_price=data.get("sl_price"),
            tp_price=data.get("tp_price"),
            status=OrderStatus(data["status"]),
            submitted_at=data["submitted_at"],
            last_updated_at=data["last_updated_at"],
            events=[OrderEvent.from_mongo(e) for e in data.get("events", [])],
            fills=[Fill.from_mongo(f, order_id=order_id) for f in data.get("fills", [])],
            resulting_trade_id=data.get("resulting_trade_id"),
        )
