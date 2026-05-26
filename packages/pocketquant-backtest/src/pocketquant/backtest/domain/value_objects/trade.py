"""Trade VO — round-trip economic outcome (entry + exit). Persisted in `backtest_trades`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Trade:
    """Round-trip economic outcome (Backtrader/QC convention).

    Flat shape (entry_* / exit_* prefix) for Mongo query simplicity — no nested
    sub-doc traversal in queries.

    `entry_order_id` and `exit_order_id` are nullable to support migrated docs
    where the original order ID was not preserved in the old PositionRecord shape.
    """

    trade_id: str
    run_id: str
    strategy_code: str
    symbol: str
    direction: str  # "LONG" | "SHORT"
    entry_order_id: str | None
    entry_price: float
    entry_time: datetime
    quantity: float
    exit_order_id: str | None
    exit_price: float
    exit_time: datetime
    sl_price: float | None
    tp_price: float | None
    pnl: float
    commission: float
    duration_seconds: float

    def to_mongo(self) -> dict[str, Any]:
        return {
            "_id": self.trade_id,
            "run_id": self.run_id,
            "strategy_code": self.strategy_code,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_order_id": self.entry_order_id,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "quantity": self.quantity,
            "exit_order_id": self.exit_order_id,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time,
            "sl_price": self.sl_price,
            "tp_price": self.tp_price,
            "pnl": self.pnl,
            "commission": self.commission,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> Trade:
        return cls(
            trade_id=data["_id"],
            run_id=data["run_id"],
            strategy_code=data["strategy_code"],
            symbol=data["symbol"],
            direction=data["direction"],
            entry_order_id=data.get("entry_order_id"),
            entry_price=data["entry_price"],
            entry_time=data["entry_time"],
            quantity=data["quantity"],
            exit_order_id=data.get("exit_order_id"),
            exit_price=data["exit_price"],
            exit_time=data["exit_time"],
            sl_price=data.get("sl_price"),
            tp_price=data.get("tp_price"),
            pnl=data.get("pnl", 0.0),
            commission=data.get("commission", 0.0),
            duration_seconds=data.get("duration_seconds", 0.0),
        )
