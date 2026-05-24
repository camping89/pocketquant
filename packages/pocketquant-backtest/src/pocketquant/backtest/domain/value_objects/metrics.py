"""BacktestMetrics VO — performance metrics computed from trade list + equity curve."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any


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
            avg_trade_duration=(
                timedelta(seconds=duration_sec) if duration_sec is not None else None
            ),
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
