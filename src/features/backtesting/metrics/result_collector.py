"""Result collector - tracks equity and trades during backtest execution."""

from datetime import datetime, timedelta

import numpy as np

from src.common.time.simulation import get_current_time
from src.features.backtesting.metrics.performance_calculator import PerformanceCalculator
from src.features.backtesting.models.backtest_config import BacktestConfig
from src.features.backtesting.models.backtest_result import (
    BacktestMetrics,
    BacktestResult,
    EquityPoint,
    TradeRecord,
)
from src.infrastructure.brokers.models import OrderResult


class BacktestResultCollector:
    """Collects trades and equity snapshots during backtest, then calculates metrics.

    Design decisions per validated requirements:
    - Equity curve records only on position changes (trade executions)
    - Commission calculated per trade using commission_bps
    - Tracks both realized P&L per trade and running equity

    Usage:
        collector = BacktestResultCollector(config, initial_capital=10000)
        # Register as callback on broker
        await broker.subscribe_order_updates(collector.on_fill)
        # After backtest completes
        result = collector.finalize(run_id, started_at, completed_at)
    """

    def __init__(self, config: BacktestConfig, initial_capital: float) -> None:
        self._config = config
        self._initial_capital = initial_capital
        self._current_equity = initial_capital

        # Track equity at each trade (validated: every trade only)
        self._equity_curve: list[EquityPoint] = []
        self._trades: list[TradeRecord] = []

        # Position tracking for P&L calculation
        self._position_qty: float = 0.0
        self._position_cost: float = 0.0  # Total cost basis
        self._total_commission: float = 0.0

        # Running peak for drawdown calculation
        self._peak_equity = initial_capital

        # Record initial equity point
        self._equity_curve.append(
            EquityPoint(
                timestamp=datetime.combine(config.start_date, datetime.min.time()),
                equity=initial_capital,
                drawdown=0.0,
            )
        )

    async def on_fill(self, result: OrderResult) -> None:
        """Handle order fill - update position, calculate P&L, record equity.

        This is registered as a callback on the PaperBroker.
        """
        if result.filled_quantity is None or result.filled_quantity <= 0:
            return

        fill_price = result.filled_price or 0.0
        fill_qty = result.filled_quantity
        timestamp = get_current_time()

        # Calculate commission for this trade
        trade_value = fill_price * fill_qty
        commission = trade_value * self._config.commission_percent
        self._total_commission += commission

        # Calculate P&L based on position direction
        pnl = self._calculate_trade_pnl(result, fill_price, fill_qty)

        # Update equity (subtract commission from equity)
        self._current_equity += pnl - commission

        # Update peak and calculate drawdown
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity

        drawdown = 0.0
        if self._peak_equity > 0:
            drawdown = (self._current_equity - self._peak_equity) / self._peak_equity

        # Record trade
        self._trades.append(
            TradeRecord(
                order_id=result.order_id,
                symbol=self._config.symbol,
                side="BUY" if self._is_buy_order(result) else "SELL",
                quantity=fill_qty,
                price=fill_price,
                commission=commission,
                pnl=pnl,
                timestamp=timestamp,
            )
        )

        # Record equity point (validated: only on position changes)
        self._equity_curve.append(
            EquityPoint(
                timestamp=timestamp,
                equity=self._current_equity,
                drawdown=drawdown,
            )
        )

    def _is_buy_order(self, result: OrderResult) -> bool:
        """Determine if order was a buy based on order_id prefix or result."""
        # In real implementation, we'd check order side from the order aggregate
        # For now, infer from position changes (positive qty change = buy)
        return "BUY" in result.order_id.upper() or self._position_qty >= 0

    def _calculate_trade_pnl(
        self, result: OrderResult, fill_price: float, fill_qty: float
    ) -> float:
        """Calculate realized P&L for this trade.

        Returns P&L from closing positions (0 for opening trades).
        """
        # This is a simplified P&L calculation
        # Full implementation would track entry/exit pairs
        # For now, calculate based on position cost basis

        # Assuming we're tracking long positions only for simplicity
        # A full implementation would need order side from the broker
        pnl = 0.0

        # If we have an existing position and this closes it
        if self._position_qty > 0:
            avg_entry = self._position_cost / self._position_qty if self._position_qty > 0 else 0
            # Selling closes position: P&L = (exit - entry) * qty
            close_qty = min(fill_qty, self._position_qty)
            pnl = (fill_price - avg_entry) * close_qty
            self._position_qty -= close_qty
            self._position_cost -= avg_entry * close_qty
        else:
            # Opening new position
            self._position_qty += fill_qty
            self._position_cost += fill_price * fill_qty

        return pnl

    def finalize(
        self,
        run_id: str,
        started_at: datetime,
        completed_at: datetime,
        status: str = "completed",
        error_message: str | None = None,
    ) -> BacktestResult:
        """Finalize backtest and calculate all metrics.

        Args:
            run_id: Unique identifier for this backtest run.
            started_at: When backtest started.
            completed_at: When backtest completed.
            status: "completed" or "failed".
            error_message: Error details if failed.

        Returns:
            Complete BacktestResult with metrics.
        """
        metrics = self._calculate_metrics(started_at, completed_at)

        # Serialize config for storage
        config_snapshot = {
            "strategy_id": self._config.strategy_id,
            "symbol": self._config.symbol,
            "exchange": self._config.exchange,
            "interval": self._config.interval,
            "start_date": self._config.start_date.isoformat(),
            "end_date": self._config.end_date.isoformat(),
            "initial_capital": self._config.initial_capital,
            "slippage_bps": self._config.slippage_bps,
            "commission_bps": self._config.commission_bps,
            "parameters": self._config.parameters,
        }

        return BacktestResult(
            id=run_id,
            strategy_id=self._config.strategy_id,
            config_snapshot=config_snapshot,
            metrics=metrics,
            equity_curve=self._equity_curve,
            trades=self._trades,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            error_message=error_message,
            parameters=self._config.parameters,
        )

    def _calculate_metrics(
        self, started_at: datetime, completed_at: datetime
    ) -> BacktestMetrics:
        """Calculate all performance metrics from collected data."""
        if not self._trades:
            return BacktestMetrics.empty()

        # Build equity array for calculations
        equity_values = np.array([p.equity for p in self._equity_curve])

        # Calculate days in backtest
        days = (self._config.end_date - self._config.start_date).days
        if days <= 0:
            days = 1

        # Extract P&L list from trades
        pnl_list = [t.pnl for t in self._trades]
        avg_win, avg_loss, winning_trades, losing_trades = (
            PerformanceCalculator.average_win_loss(pnl_list)
        )

        # Gross profit and loss for profit factor
        gross_profit = sum(p for p in pnl_list if p > 0)
        gross_loss = abs(sum(p for p in pnl_list if p < 0))

        # Calculate average trade duration
        avg_duration = self._calculate_avg_trade_duration()

        return BacktestMetrics(
            total_return=PerformanceCalculator.total_return(
                self._initial_capital, self._current_equity
            ),
            cagr=PerformanceCalculator.cagr(
                self._initial_capital, self._current_equity, days
            ),
            sharpe_ratio=PerformanceCalculator.sharpe_ratio(equity_values),
            sortino_ratio=PerformanceCalculator.sortino_ratio(equity_values),
            max_drawdown=PerformanceCalculator.max_drawdown(equity_values),
            win_rate=PerformanceCalculator.win_rate(winning_trades, len(self._trades)),
            profit_factor=PerformanceCalculator.profit_factor(gross_profit, gross_loss),
            total_trades=len(self._trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade_duration=avg_duration,
            total_commission=self._total_commission,
        )

    def _calculate_avg_trade_duration(self) -> timedelta | None:
        """Calculate average time between entry and exit trades."""
        if len(self._trades) < 2:
            return None

        # Simple approach: average time between consecutive trades
        durations = []
        for i in range(1, len(self._trades)):
            delta = self._trades[i].timestamp - self._trades[i - 1].timestamp
            durations.append(delta.total_seconds())

        if not durations:
            return None

        avg_seconds = sum(durations) / len(durations)
        return timedelta(seconds=avg_seconds)
