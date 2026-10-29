from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from pocketquant.core.domain.trading.value_objects import (
    EquityPoint,
    PerformanceMetrics,
    Trade,
)

# Crypto markets trade 365 days
TRADING_DAYS_PER_YEAR = 365
# Risk-free rate assumption (can be parameterized later)
RISK_FREE_RATE = 0.0


class PerformanceCalculatorDomainService:
    @staticmethod
    def total_return(initial_equity: float, final_equity: float) -> float:
        if initial_equity <= 0:
            return 0.0
        return (final_equity - initial_equity) / initial_equity

    # Wall-clock days per year on purpose, not a calendar's session count: 312 daily bars
    # for Exness FX would stretch one real year into 1.17 and report a doubling as 81%.
    # Sharpe and Sortino count return observations, so they do take periods_per_year.
    @staticmethod
    def cagr(initial_equity: float, final_equity: float, days: int) -> float:
        if initial_equity <= 0 or final_equity <= 0 or days <= 0:
            return 0.0

        years = days / TRADING_DAYS_PER_YEAR
        if years <= 0:
            return 0.0

        return (final_equity / initial_equity) ** (1 / years) - 1

    # periods_per_year is keyword-only so it never collides with risk_free_rate. Flat bars
    # are in the curve, so this measures whole-period capital efficiency, not active risk.
    @staticmethod
    def sharpe_ratio(
        equity_curve: np.ndarray,
        *,
        periods_per_year: float,
        risk_free_rate: float = RISK_FREE_RATE,
    ) -> float:
        if len(equity_curve) < 2:
            return 0.0

        prev = equity_curve[:-1]
        returns = np.divide(
            np.diff(equity_curve),
            prev,
            out=np.zeros(len(prev), dtype=float),
            where=prev != 0,
        )

        # Sample std (ddof=1) needs ≥2 returns; one return divides by zero.
        if len(returns) < 2:
            return 0.0

        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)  # Sample std

        if std_return == 0 or np.isnan(std_return):
            return 0.0

        annual_return = mean_return * periods_per_year
        annual_std = std_return * np.sqrt(periods_per_year)

        return (annual_return - risk_free_rate) / annual_std

    @staticmethod
    def sortino_ratio(
        equity_curve: np.ndarray,
        *,
        periods_per_year: float,
        risk_free_rate: float = RISK_FREE_RATE,
    ) -> float:
        if len(equity_curve) < 2:
            return 0.0

        prev = equity_curve[:-1]
        returns = np.divide(
            np.diff(equity_curve),
            prev,
            out=np.zeros(len(prev), dtype=float),
            where=prev != 0,
        )

        if len(returns) < 2:
            return 0.0

        mean_return = np.mean(returns)

        downside_returns = returns[returns < 0]

        if len(downside_returns) == 0:
            # No downside = infinite Sortino, cap at high value
            return 10.0 if mean_return > 0 else 0.0

        # Sample std (ddof=1) needs ≥2 downside returns; one divides by zero.
        if len(downside_returns) < 2:
            return 0.0

        downside_std = np.std(downside_returns, ddof=1)

        if downside_std == 0 or np.isnan(downside_std):
            return 0.0

        annual_return = mean_return * periods_per_year
        annual_downside_std = downside_std * np.sqrt(periods_per_year)

        return (annual_return - risk_free_rate) / annual_downside_std

    @staticmethod
    def max_drawdown(equity_curve: np.ndarray) -> float:
        if len(equity_curve) < 2:
            return 0.0

        cummax = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - cummax) / cummax
        drawdown = np.nan_to_num(drawdown, nan=0.0)

        return float(np.min(drawdown))  # Most negative value

    @staticmethod
    def drawdown_series(equity_curve: np.ndarray) -> np.ndarray:
        if len(equity_curve) < 1:
            return np.array([])

        cummax = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - cummax) / cummax
        return np.nan_to_num(drawdown, nan=0.0)

    @staticmethod
    def win_rate(winning_trades: int, total_trades: int) -> float:
        if total_trades == 0:
            return 0.0
        return winning_trades / total_trades

    @staticmethod
    def profit_factor(gross_profit: float, gross_loss: float) -> float:
        if gross_loss <= 0:
            return 100.0 if gross_profit > 0 else 0.0
        return min(gross_profit / gross_loss, 100.0)

    @staticmethod
    def average_win_loss(pnl_list: list[float]) -> tuple[float, float, int, int]:
        if not pnl_list:
            return 0.0, 0.0, 0, 0

        wins = [p for p in pnl_list if p > 0]
        losses = [p for p in pnl_list if p < 0]

        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        return avg_win, avg_loss, len(wins), len(losses)

    # equity_curve (realized) drives total_return/cagr/max_drawdown; returns_curve (per-bar
    # mark-to-market) drives Sharpe/Sortino so they annualize on evenly sampled returns.
    # periods_per_year None skips annualization (Sharpe/Sortino = 0).
    @staticmethod
    def build(
        closed_trades: list[Trade],
        equity_curve: list[EquityPoint],
        initial_capital: float,
        current_equity: float,
        total_commission: float,
        start_date: datetime,
        end_date: datetime,
        periods_per_year: float | None,
        returns_curve: list[EquityPoint] | None = None,
    ) -> PerformanceMetrics:
        if not closed_trades:
            return PerformanceMetrics.empty()

        equity_values = np.array([p.equity for p in equity_curve])
        returns_source = returns_curve if returns_curve else equity_curve
        returns_values = np.array([p.equity for p in returns_source])
        days = max((end_date - start_date).days, 1)

        if periods_per_year is None:
            sharpe = 0.0
            sortino = 0.0
        else:
            sharpe = PerformanceCalculatorDomainService.sharpe_ratio(
                returns_values, periods_per_year=periods_per_year
            )
            sortino = PerformanceCalculatorDomainService.sortino_ratio(
                returns_values, periods_per_year=periods_per_year
            )

        pnl_list = [t.pnl for t in closed_trades]
        avg_win, avg_loss, winning, losing = PerformanceCalculatorDomainService.average_win_loss(
            pnl_list
        )
        gross_profit = sum(p for p in pnl_list if p > 0)
        gross_loss = abs(sum(p for p in pnl_list if p < 0))
        avg_duration = _avg_trade_duration(closed_trades)

        return PerformanceMetrics(
            total_return=PerformanceCalculatorDomainService.total_return(
                initial_capital, current_equity
            ),
            cagr=PerformanceCalculatorDomainService.cagr(initial_capital, current_equity, days),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=PerformanceCalculatorDomainService.max_drawdown(equity_values),
            win_rate=PerformanceCalculatorDomainService.win_rate(winning, len(closed_trades)),
            profit_factor=PerformanceCalculatorDomainService.profit_factor(
                gross_profit, gross_loss
            ),
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
