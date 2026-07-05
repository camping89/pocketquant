"""Backtest value objects (Backtrader / QuantConnect naming).

Consolidated single-file module (was a per-file ``value_objects/`` package):

- ``Fill``                    — atomic execution event
- ``Trade``                   — round-trip outcome (closed entry + exit)
- ``Order``                   — order intent with lifecycle audit trail
- ``OpenLot``                 — still-open lot snapshot at run-end
- ``EquityPoint``             — equity curve point
- ``BacktestMetrics``         — performance summary

``OrderEvent`` (the lifecycle audit record embedded in ``Order.events[]``) is
defined alongside the broker port DTOs so the emitter (PaperBrokerAdapter) and the
consumer (backtest collector) share one definition. It is imported here for the
``Order`` typing but is NOT re-exported as a backtest alias — consumers import
``OrderEvent`` from its own module directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from pocketquant.core.domain.brokers.events import OrderEvent
from pocketquant.core.domain.order.enums import OrderSide, OrderStatus, OrderType


@dataclass
class EquityPoint:
    timestamp: datetime
    equity: float
    drawdown: float  # Current drawdown from peak (negative value)

    def to_mongo(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "equity": self.equity,
            "drawdown": self.drawdown,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> EquityPoint:
        return cls(
            timestamp=data["timestamp"],
            equity=data["equity"],
            drawdown=data.get("drawdown", 0.0),
        )


@dataclass
class Fill:
    """Atomic execution event (Backtrader/QC convention).

    Embedded in `Order.fills[]`. `order_id` is redundant when embedded but kept
    so a standalone Fill carries its parent reference.
    """

    fill_id: UUID
    order_id: str  # FK to parent Order — reference value, stays str
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
            "fill_id": str(self.fill_id),
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
        resolved_order_id = data.get("order_id") or order_id
        if not resolved_order_id:
            raise ValueError(
                "Fill must have order_id (present in doc or passed as kwarg for embedded fills)"
            )
        return cls(
            fill_id=UUID(data["fill_id"]),
            order_id=resolved_order_id,
            symbol=data["symbol"],
            side=OrderSide(data["side"]),
            quantity=data["quantity"],
            price=data["price"],
            commission=data.get("commission", 0.0),
            slippage=data.get("slippage", 0.0),
            timestamp=data["timestamp"],
        )


@dataclass
class Order:
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
    def from_mongo(cls, data: dict[str, Any]) -> Order:
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


@dataclass
class OpenLot:
    """Snapshot of a still-open lot at end of run.

    Embedded in `backtest_runs.open_positions[]`. Differs from `Trade` in that
    there is no exit yet — only entry-side information.

    `entry_order_id` is nullable to support migrated docs where the original
    order ID could not be reconstructed from old PositionRecord shape.
    `entry_commission_portion` is the commission attributable to the still-open
    quantity (commission scaled by qty_remaining / qty_original).
    """

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


@dataclass
class Trade:
    """Round-trip economic outcome (Backtrader/QC convention).

    Flat shape (entry_* / exit_* prefix) for Mongo query simplicity — no nested
    sub-doc traversal in queries.

    `entry_order_id` and `exit_order_id` are nullable to support migrated docs
    where the original order ID was not preserved in the old PositionRecord shape.
    """

    trade_id: UUID
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
            "_id": str(self.trade_id),
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
            trade_id=UUID(data["_id"]),
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


@dataclass
class BacktestMetrics:
    total_return: float  # (final - initial) / initial
    cagr: float  # Compound Annual Growth Rate
    sharpe_ratio: float  # Risk-adjusted return
    sortino_ratio: float  # Downside risk-adjusted return
    max_drawdown: float  # Maximum peak-to-trough decline (negative)
    win_rate: float  # Winning trades / total trades
    profit_factor: float  # Gross profit / gross loss
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float  # Average winning trade P&L
    avg_loss: float  # Average losing trade P&L (negative)
    avg_trade_duration: timedelta | None  # Average trade holding time
    total_commission: float

    def to_dict(self) -> dict[str, Any]:
        return self.to_mongo()

    def to_mongo(self) -> dict[str, Any]:
        return {
            "total_return": self.total_return,
            "cagr": self.cagr,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "avg_trade_duration_seconds": (
                self.avg_trade_duration.total_seconds() if self.avg_trade_duration else None
            ),
            "total_commission": self.total_commission,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> BacktestMetrics:
        duration_sec = data.get("avg_trade_duration_seconds")
        return cls(
            total_return=data["total_return"],
            cagr=data["cagr"],
            sharpe_ratio=data["sharpe_ratio"],
            sortino_ratio=data["sortino_ratio"],
            max_drawdown=data["max_drawdown"],
            win_rate=data["win_rate"],
            profit_factor=data["profit_factor"],
            total_trades=data["total_trades"],
            winning_trades=data["winning_trades"],
            losing_trades=data["losing_trades"],
            avg_win=data["avg_win"],
            avg_loss=data["avg_loss"],
            avg_trade_duration=(
                timedelta(seconds=duration_sec) if duration_sec is not None else None
            ),
            total_commission=data.get("total_commission", 0.0),
        )

    @classmethod
    def empty(cls) -> BacktestMetrics:
        return cls(
            total_return=0.0,
            cagr=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            avg_win=0.0,
            avg_loss=0.0,
            avg_trade_duration=None,
            total_commission=0.0,
        )
