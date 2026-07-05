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
    """Static methods for calculating backtest performance metrics.

    All methods handle edge cases gracefully (empty data, division by zero).
    Uses NumPy for efficient vectorized calculations.
    """

    @staticmethod
    def total_return(initial_equity: float, final_equity: float) -> float:
        """Calculate total return as percentage.

        Returns:
            Total return (e.g., 0.25 for 25% gain, -0.10 for 10% loss).
        """
        if initial_equity <= 0:
            return 0.0
        return (final_equity - initial_equity) / initial_equity

    @staticmethod
    def cagr(initial_equity: float, final_equity: float, days: int) -> float:
        """Calculate Compound Annual Growth Rate.

        Args:
            initial_equity: Starting equity.
            final_equity: Ending equity.
            days: Number of calendar days in backtest period.

        Returns:
            CAGR as decimal (e.g., 0.15 for 15% annual growth).
        """
        if initial_equity <= 0 or final_equity <= 0 or days <= 0:
            return 0.0

        years = days / TRADING_DAYS_PER_YEAR
        if years <= 0:
            return 0.0

        return (final_equity / initial_equity) ** (1 / years) - 1

    @staticmethod
    def sharpe_ratio(
        equity_curve: np.ndarray,
        *,
        periods_per_year: float,
        risk_free_rate: float = RISK_FREE_RATE,
    ) -> float:
        """Calculate annualized Sharpe ratio from a per-bar equity curve.

        Sharpe = (mean return - risk free rate) / volatility, annualized by the
        number of bars per year for the backtest interval.

        ``periods_per_year`` is **keyword-only** so it never positionally
        collides with ``risk_free_rate``.

        Caveat (per-bar definition): the equity curve carries one point per bar,
        including flat bars with no open position. Those flat bars dilute the
        return std, so this Sharpe measures whole-period **capital efficiency**,
        not active-position risk. This is the industry-standard per-bar
        definition and is comparable across strategies on the same interval.

        Args:
            equity_curve: Array of equity values, one per bar.
            periods_per_year: Bars per year for the interval (Interval.periods_per_year).
            risk_free_rate: Annual risk-free rate (default 0).

        Returns:
            Annualized Sharpe ratio.
        """
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
        """Calculate annualized Sortino ratio from a per-bar equity curve.

        Sortino = (mean return - risk free rate) / downside volatility, annualized
        by the number of bars per year for the backtest interval. Only penalizes
        negative returns (downside deviation). ``periods_per_year`` is
        keyword-only (see ``sharpe_ratio``).

        Args:
            equity_curve: Array of equity values, one per bar.
            periods_per_year: Bars per year for the interval (Interval.periods_per_year).
            risk_free_rate: Annual risk-free rate (default 0).

        Returns:
            Annualized Sortino ratio.
        """
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
        """Calculate maximum drawdown from equity curve.

        Max drawdown is the largest peak-to-trough decline.

        Args:
            equity_curve: Array of equity values over time.

        Returns:
            Maximum drawdown as negative decimal (e.g., -0.20 for 20% drawdown).
        """
        if len(equity_curve) < 2:
            return 0.0

        cummax = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - cummax) / cummax
        drawdown = np.nan_to_num(drawdown, nan=0.0)

        return float(np.min(drawdown))  # Most negative value

    @staticmethod
    def drawdown_series(equity_curve: np.ndarray) -> np.ndarray:
        """Calculate drawdown at each point in equity curve.

        Args:
            equity_curve: Array of equity values over time.

        Returns:
            Array of drawdown values (negative decimals).
        """
        if len(equity_curve) < 1:
            return np.array([])

        cummax = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - cummax) / cummax
        return np.nan_to_num(drawdown, nan=0.0)

    @staticmethod
    def win_rate(winning_trades: int, total_trades: int) -> float:
        """Calculate win rate.

        Returns:
            Win rate as decimal (e.g., 0.55 for 55% win rate).
        """
        if total_trades == 0:
            return 0.0
        return winning_trades / total_trades

    @staticmethod
    def profit_factor(gross_profit: float, gross_loss: float) -> float:
        """Calculate profit factor (gross profit / gross loss).

        Args:
            gross_profit: Sum of all winning trade P&L (positive).
            gross_loss: Sum of all losing trade P&L (should be positive for calculation).

        Returns:
            Profit factor. Returns 0 if no losses, infinity capped at 100.
        """
        if gross_loss <= 0:
            return 100.0 if gross_profit > 0 else 0.0
        return min(gross_profit / gross_loss, 100.0)

    @staticmethod
    def average_win_loss(pnl_list: list[float]) -> tuple[float, float, int, int]:
        """Calculate average win and loss from P&L list.

        Args:
            pnl_list: List of individual trade P&L values.

        Returns:
            Tuple of (avg_win, avg_loss, winning_count, losing_count).
            avg_loss is returned as negative.
        """
        if not pnl_list:
            return 0.0, 0.0, 0, 0

        wins = [p for p in pnl_list if p > 0]
        losses = [p for p in pnl_list if p < 0]

        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        return avg_win, avg_loss, len(wins), len(losses)

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
        """Build metrics. ``equity_curve`` (realized, trade-keyed) drives
        total_return/cagr/max_drawdown; ``returns_curve`` (per-bar mark-to-market,
        when supplied) drives Sharpe/Sortino so they annualize on evenly-sampled
        returns. ``periods_per_year`` of None (unknown interval) skips annualization
        → Sharpe/Sortino = 0.
        """
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
