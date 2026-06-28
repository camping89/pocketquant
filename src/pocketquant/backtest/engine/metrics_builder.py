from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from pocketquant.backtest.domain.services.performance_calculator import PerformanceCalculator
from pocketquant.core.domain.backtest import BacktestMetrics, EquityPoint, Trade


def build_metrics(
    closed_trades: list[Trade],
    equity_curve: list[EquityPoint],
    initial_capital: float,
    current_equity: float,
    total_commission: float,
    start_date: date,
    end_date: date,
    periods_per_year: float | None,
    returns_curve: list[EquityPoint] | None = None,
) -> BacktestMetrics:
    """Build metrics. ``equity_curve`` (realized, trade-keyed) drives
    total_return/cagr/max_drawdown; ``returns_curve`` (per-bar mark-to-market,
    when supplied) drives Sharpe/Sortino so they annualize on evenly-sampled
    returns. ``periods_per_year`` of None (unknown interval) skips annualization
    → Sharpe/Sortino = 0.
    """
    if not closed_trades:
        return BacktestMetrics.empty()

    equity_values = np.array([p.equity for p in equity_curve])
    returns_source = returns_curve if returns_curve else equity_curve
    returns_values = np.array([p.equity for p in returns_source])
    days = max((end_date - start_date).days, 1)

    if periods_per_year is None:
        sharpe = 0.0
        sortino = 0.0
    else:
        sharpe = PerformanceCalculator.sharpe_ratio(
            returns_values, periods_per_year=periods_per_year
        )
        sortino = PerformanceCalculator.sortino_ratio(
            returns_values, periods_per_year=periods_per_year
        )

    pnl_list = [t.pnl for t in closed_trades]
    avg_win, avg_loss, winning, losing = PerformanceCalculator.average_win_loss(pnl_list)
    gross_profit = sum(p for p in pnl_list if p > 0)
    gross_loss = abs(sum(p for p in pnl_list if p < 0))
    avg_duration = _avg_trade_duration(closed_trades)

    return BacktestMetrics(
        total_return=PerformanceCalculator.total_return(initial_capital, current_equity),
        cagr=PerformanceCalculator.cagr(initial_capital, current_equity, days),
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=PerformanceCalculator.max_drawdown(equity_values),
        win_rate=PerformanceCalculator.win_rate(winning, len(closed_trades)),
        profit_factor=PerformanceCalculator.profit_factor(gross_profit, gross_loss),
        total_trades=len(closed_trades),
        winning_trades=winning,
        losing_trades=losing,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_trade_duration=avg_duration,
        total_commission=total_commission,
    )


def _avg_trade_duration(closed: list[Trade]) -> timedelta | None:
    if not closed:
        return None
    seconds = [t.duration_seconds for t in closed if t.duration_seconds > 0]
    if not seconds:
        return None
    return timedelta(seconds=sum(seconds) / len(seconds))
