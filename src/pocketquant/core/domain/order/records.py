"""Order audit record — persisted order intent with lifecycle trail.

``OrderRecord`` is the flat, persisted audit shape for the ``backtest_orders``
collection: an order intent with embedded ``events[]`` (lifecycle transitions)
and ``fills[]`` (executions). Distinct from ``OrderAggregate`` (the live
state-machine entity) — this one is a snapshot record, not a behavioral root.

``OrderEvent`` is defined alongside the broker port DTOs so the emitter
(PaperBrokerAdapter) and the consumer (backtest collector) share one definition.
``Fill`` is a universal, source-agnostic contract in ``core.domain.trading``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pocketquant.core.domain.brokers.events import OrderEvent
from pocketquant.core.domain.order.enums import OrderSide, OrderStatus, OrderType

if TYPE_CHECKING:
    # Runtime import is deferred into from_mongo to break the package-init cycle:
    # order/__init__ → records → trading.value_objects → order.enums → order/__init__.
    from pocketquant.core.domain.trading.value_objects import Fill


@dataclass
class OrderRecord:
    """Order intent with full lifecycle (Backtrader/QC convention).

    Persisted standalone in `backtest_orders` with `events[]` + `fills[]` embedded.
    Side / type / status typed as core enums (not bare strings) for safety.
    """

    order_id: UUID
    run_id: str
    strategy_code: str
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
            "_id": str(self.order_id),
            "run_id": self.run_id,
            "strategy_code": self.strategy_code,
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
    def from_mongo(cls, data: dict[str, Any]) -> OrderRecord:
        from pocketquant.core.domain.trading.value_objects import Fill

        # Keep the raw str for embedded fills — their order_id FK stays str.
        raw_order_id = data["_id"]
        return cls(
            order_id=UUID(raw_order_id),
            run_id=data["run_id"],
            strategy_code=data["strategy_code"],
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
            fills=[Fill.from_mongo(f, order_id=raw_order_id) for f in data.get("fills", [])],
            resulting_trade_id=data.get("resulting_trade_id"),
        )
