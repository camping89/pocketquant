"""Optimization configuration for grid search parameter sweeps."""

from dataclasses import dataclass
from datetime import date
from typing import Any

# Maximum combinations allowed (validated requirement: 1000)
MAX_COMBINATIONS = 1000


@dataclass
class OptimizationConfig:
    """Configuration for grid search optimization.

    Extends BacktestConfig concept with parameter grid and target metric.

    Attributes:
        strategy_code: Strategy identifier to optimize.
        symbol: Composite trading symbol ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
        interval: Bar interval.
        start_date: Start date for backtests.
        end_date: End date for backtests.
        initial_capital: Starting capital for each backtest.
        slippage_bps: Slippage in basis points.
        commission_bps: Commission in basis points.
        parameter_grid: Dict of parameter names to list of values to test.
        target_metric: Metric to maximize (e.g., "sharpe_ratio").
        max_workers: Maximum concurrent backtests.
    """

    strategy_code: str
    symbol: str
    interval: str
    start_date: date
    end_date: date
    parameter_grid: dict[str, list[Any]]
    initial_capital: float = 10_000.0
    slippage_bps: float = 10.0
    commission_bps: float = 10.0
    target_metric: str = "sharpe_ratio"
    max_workers: int = 4

    def get_total_combinations(self) -> int:
        """Calculate total number of parameter combinations."""
        if not self.parameter_grid:
            return 0

        total = 1
        for values in self.parameter_grid.values():
            total *= len(values)
        return total

    def validate(self) -> None:
        """Validate configuration, raise ValueError if invalid."""
        combinations = self.get_total_combinations()

        if combinations == 0:
            raise ValueError("parameter_grid must have at least one parameter with values")

        if combinations > MAX_COMBINATIONS:
            raise ValueError(
                f"Too many combinations ({combinations}). "
                f"Maximum allowed is {MAX_COMBINATIONS}. "
                "Reduce parameter ranges or use fewer parameters."
            )

        valid_metrics = [
            "sharpe_ratio",
            "sortino_ratio",
            "total_return",
            "cagr",
            "profit_factor",
            "win_rate",
        ]
        if self.target_metric not in valid_metrics:
            raise ValueError(
                f"Invalid target_metric: {self.target_metric}. Valid options: {valid_metrics}"
            )

        if self.max_workers < 1:
            raise ValueError("max_workers must be at least 1")

        if self.max_workers > 16:
            raise ValueError("max_workers cannot exceed 16 (resource protection)")
