"""Backtest value objects - trade records, equity points, metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class TradeRecord:
    """Internal record of a single order fill during backtest."""

    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    price: float
    commission: float
    pnl: float
    timestamp: datetime
    sl_price: float | None = None
    tp_price: float | None = None

    def to_mongo(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "commission": self.commission,
            "pnl": self.pnl,
            "timestamp": self.timestamp,
            "sl_price": self.sl_price,
            "tp_price": self.tp_price,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> TradeRecord:
        return cls(
            order_id=data["order_id"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=data["quantity"],
            price=data["price"],
            commission=data.get("commission", 0.0),
            pnl=data["pnl"],
            timestamp=data["timestamp"],
            sl_price=data.get("sl_price"),
            tp_price=data.get("tp_price"),
        )


@dataclass
class PositionRecord:
    """Completed or open position — one BUY/SELL pair aggregated for the API."""

    symbol: str
    entry_price: float
    entry_time: datetime
    quantity: float
    sl_price: float | None
    tp_price: float | None
    exit_price: float | None  # None if still open
    exit_time: datetime | None  # None if still open
    pnl: float
    commission: float  # combined entry + exit commission

    def to_mongo(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "quantity": self.quantity,
            "sl_price": self.sl_price,
            "tp_price": self.tp_price,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time,
            "pnl": self.pnl,
            "commission": self.commission,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> PositionRecord:
        return cls(
            symbol=data["symbol"],
            entry_price=data["entry_price"],
            entry_time=data["entry_time"],
            quantity=data["quantity"],
            sl_price=data.get("sl_price"),
            tp_price=data.get("tp_price"),
            exit_price=data.get("exit_price"),
            exit_time=data.get("exit_time"),
            pnl=data.get("pnl", 0.0),
            commission=data.get("commission", 0.0),
        )


@dataclass
class EquityPoint:
    """Single point on the equity curve (recorded on position changes only)."""

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
class BacktestMetrics:
    """Performance metrics calculated from backtest results."""

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
        """Alias for API serialization."""
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
            avg_trade_duration=timedelta(seconds=duration_sec) if duration_sec else None,
            total_commission=data.get("total_commission", 0.0),
        )

    @classmethod
    def empty(cls) -> BacktestMetrics:
        """Return empty metrics for failed or no-trade backtests."""
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


@dataclass
class OptimizationResultEntry:
    """Single entry in optimization results - one parameter combination."""

    parameters: dict[str, Any]
    metrics: BacktestMetrics
    backtest_id: str
    rank: int  # 1 = best

    def to_mongo(self) -> dict[str, Any]:
        return {
            "parameters": self.parameters,
            "metrics": self.metrics.to_mongo(),
            "backtest_id": self.backtest_id,
            "rank": self.rank,
        }

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> OptimizationResultEntry:
        return cls(
            parameters=data["parameters"],
            metrics=BacktestMetrics.from_mongo(data["metrics"]),
            backtest_id=data["backtest_id"],
            rank=data["rank"],
        )
