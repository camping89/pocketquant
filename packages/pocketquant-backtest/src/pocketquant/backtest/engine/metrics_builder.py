"""Build BacktestMetrics from closed PositionRecords + equity curve.

Extracted from BacktestResultCollector to keep result_collector under 200 LOC.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
from pocketquant.backtest.domain import BacktestMetrics, EquityPoint, PositionRecord
from pocketquant.backtest.domain.services.performance_calculator import PerformanceCalculator


def build_metrics(
    closed_positions: list[PositionRecord],
    equity_curve: list[EquityPoint],
    initial_capital: float,
    current_equity: float,
    total_commission: float,
    start_date: date,
    end_date: date,
) -> BacktestMetrics:
    """Compute aggregate performance metrics for a finished backtest."""
    if not closed_positions:
        return BacktestMetrics.empty()

    equity_values = np.array([p.equity for p in equity_curve])
    days = max((end_date - start_date).days, 1)

    pnl_list = [p.pnl for p in closed_positions]
    avg_win, avg_loss, winning, losing = PerformanceCalculator.average_win_loss(pnl_list)
    gross_profit = sum(p for p in pnl_list if p > 0)
    gross_loss = abs(sum(p for p in pnl_list if p < 0))
    avg_duration = _avg_trade_duration(closed_positions)

    return BacktestMetrics(
        total_return=PerformanceCalculator.total_return(initial_capital, current_equity),
        cagr=PerformanceCalculator.cagr(initial_capital, current_equity, days),
        sharpe_ratio=PerformanceCalculator.sharpe_ratio(equity_values),
        sortino_ratio=PerformanceCalculator.sortino_ratio(equity_values),
        max_drawdown=PerformanceCalculator.max_drawdown(equity_values),
        win_rate=PerformanceCalculator.win_rate(winning, len(closed_positions)),
        profit_factor=PerformanceCalculator.profit_factor(gross_profit, gross_loss),
        total_trades=len(closed_positions),
        winning_trades=winning,
        losing_trades=losing,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_trade_duration=avg_duration,
        total_commission=total_commission,
    )


def _avg_trade_duration(closed: list[PositionRecord]) -> timedelta | None:
    durations = [
        (p.exit_time - p.entry_time).total_seconds()
        for p in closed
        if p.exit_time is not None
    ]
    if not durations:
        return None
    return timedelta(seconds=sum(durations) / len(durations))
