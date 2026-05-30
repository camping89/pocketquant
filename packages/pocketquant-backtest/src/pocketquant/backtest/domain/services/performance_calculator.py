import numpy as np

# Crypto markets trade 365 days
TRADING_DAYS_PER_YEAR = 365
# Risk-free rate assumption (can be parameterized later)
RISK_FREE_RATE = 0.0


class PerformanceCalculator:
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
    def sharpe_ratio(equity_curve: np.ndarray, risk_free_rate: float = RISK_FREE_RATE) -> float:
        """Calculate annualized Sharpe ratio from equity curve.

        Sharpe = (mean return - risk free rate) / volatility

        Args:
            equity_curve: Array of equity values over time.
            risk_free_rate: Annual risk-free rate (default 0).

        Returns:
            Annualized Sharpe ratio.
        """
        if len(equity_curve) < 2:
            return 0.0

        returns = np.diff(equity_curve) / equity_curve[:-1]

        if len(returns) == 0:
            return 0.0

        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)  # Sample std

        if std_return == 0 or np.isnan(std_return):
            return 0.0

        annual_return = mean_return * TRADING_DAYS_PER_YEAR
        annual_std = std_return * np.sqrt(TRADING_DAYS_PER_YEAR)

        return (annual_return - risk_free_rate) / annual_std

    @staticmethod
    def sortino_ratio(equity_curve: np.ndarray, risk_free_rate: float = RISK_FREE_RATE) -> float:
        """Calculate annualized Sortino ratio from equity curve.

        Sortino = (mean return - risk free rate) / downside volatility
        Only penalizes negative returns (downside deviation).

        Args:
            equity_curve: Array of equity values over time.
            risk_free_rate: Annual risk-free rate (default 0).

        Returns:
            Annualized Sortino ratio.
        """
        if len(equity_curve) < 2:
            return 0.0

        returns = np.diff(equity_curve) / equity_curve[:-1]

        if len(returns) == 0:
            return 0.0

        mean_return = np.mean(returns)

        downside_returns = returns[returns < 0]

        if len(downside_returns) == 0:
            # No downside = infinite Sortino, cap at high value
            return 10.0 if mean_return > 0 else 0.0

        downside_std = np.std(downside_returns, ddof=1)

        if downside_std == 0 or np.isnan(downside_std):
            return 0.0

        annual_return = mean_return * TRADING_DAYS_PER_YEAR
        annual_downside_std = downside_std * np.sqrt(TRADING_DAYS_PER_YEAR)

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
