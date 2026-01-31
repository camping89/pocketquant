"""CQRS commands and queries for backtesting feature."""

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class RunBacktestCommand:
    """Command to execute a single backtest run."""

    strategy_id: str
    symbol: str
    exchange: str
    interval: str
    start_date: date
    end_date: date
    initial_capital: float = 10_000.0
    slippage_bps: float = 10.0
    commission_bps: float = 10.0
    parameters: dict[str, Any] | None = None


@dataclass
class RunOptimizationCommand:
    """Command to run grid optimization across parameter combinations."""

    strategy_id: str
    symbol: str
    exchange: str
    interval: str
    start_date: date
    end_date: date
    parameter_grid: dict[str, list[Any]]
    initial_capital: float = 10_000.0
    slippage_bps: float = 10.0
    commission_bps: float = 10.0
    target_metric: str = "sharpe_ratio"
    max_workers: int = 4


@dataclass
class GetBacktestQuery:
    """Query to get a specific backtest result by ID."""

    run_id: str


@dataclass
class GetOptimizationQuery:
    """Query to get a specific optimization result by ID."""

    optimization_id: str


@dataclass
class ListBacktestsQuery:
    """Query to list backtest results for a strategy."""

    strategy_id: str
    limit: int = 20
    include_failed: bool = False
