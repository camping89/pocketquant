"""Backtest result models - metrics, trades, and run results."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class TradeRecord:
    """Record of a single trade execution during backtest."""

    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    price: float
    commission: float
    pnl: float  # Realized P&L for this trade
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "commission": self.commission,
            "pnl": self.pnl,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TradeRecord":
        """Create from dictionary."""
        return cls(
            order_id=data["order_id"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=data["quantity"],
            price=data["price"],
            commission=data.get("commission", 0.0),
            pnl=data["pnl"],
            timestamp=data["timestamp"],
        )


@dataclass
class EquityPoint:
    """Single point on the equity curve (recorded on position changes only)."""

    timestamp: datetime
    equity: float
    drawdown: float  # Current drawdown from peak (negative value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "equity": self.equity,
            "drawdown": self.drawdown,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EquityPoint":
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
                self.avg_trade_duration.total_seconds()
                if self.avg_trade_duration
                else None
            ),
            "total_commission": self.total_commission,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BacktestMetrics":
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
    def empty(cls) -> "BacktestMetrics":
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
class BacktestResult:
    """Complete result of a backtest run with metrics and equity curve."""

    id: str
    strategy_id: str
    config_snapshot: dict[str, Any]  # Serialized BacktestConfig
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
    started_at: datetime
    completed_at: datetime
    status: str  # "completed", "failed"
    error_message: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)  # For optimizer

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "_id": self.id,
            "strategy_id": self.strategy_id,
            "config_snapshot": self.config_snapshot,
            "metrics": self.metrics.to_dict(),
            "equity_curve": [p.to_dict() for p in self.equity_curve],
            "trades": [t.to_dict() for t in self.trades],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "error_message": self.error_message,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BacktestResult":
        """Create from MongoDB document."""
        return cls(
            id=data["_id"],
            strategy_id=data["strategy_id"],
            config_snapshot=data["config_snapshot"],
            metrics=BacktestMetrics.from_dict(data["metrics"]),
            equity_curve=[EquityPoint.from_dict(p) for p in data.get("equity_curve", [])],
            trades=[TradeRecord.from_dict(t) for t in data.get("trades", [])],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            status=data["status"],
            error_message=data.get("error_message"),
            parameters=data.get("parameters", {}),
        )
