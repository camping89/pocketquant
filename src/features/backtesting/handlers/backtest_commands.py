"""CQRS commands and queries for backtesting feature."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class RunBacktestCommand(BaseModel):
    """Command to execute a single backtest run."""

    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSDT)")
    exchange: str = Field(..., description="Exchange name (e.g., OKX)")
    interval: str = Field(..., description="Bar interval (e.g., 5m, 1h)")
    start_date: date = Field(..., description="Backtest start date")
    end_date: date = Field(..., description="Backtest end date")
    initial_capital: float = Field(default=10_000.0, ge=100, description="Starting capital")
    slippage_bps: float = Field(default=10.0, ge=0, description="Slippage in basis points")
    commission_bps: float = Field(default=10.0, ge=0, description="Commission in basis points")
    parameters: dict[str, Any] | None = Field(default=None, description="Strategy parameters")


class RunOptimizationCommand(BaseModel):
    """Command to run grid optimization across parameter combinations."""

    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")
    interval: str = Field(..., description="Bar interval")
    start_date: date = Field(..., description="Backtest start date")
    end_date: date = Field(..., description="Backtest end date")
    parameter_grid: dict[str, list[Any]] = Field(
        ..., description="Parameter grid (e.g., {'ma_fast': [5,10,20]})"
    )
    initial_capital: float = Field(default=10_000.0, ge=100)
    slippage_bps: float = Field(default=10.0, ge=0)
    commission_bps: float = Field(default=10.0, ge=0)
    target_metric: str = Field(default="sharpe_ratio", description="Metric to optimize")
    max_workers: int = Field(default=4, ge=1, le=16, description="Max concurrent backtests")


class GetBacktestQuery(BaseModel):
    """Query to get a specific backtest result by ID."""

    run_id: str


class GetOptimizationQuery(BaseModel):
    """Query to get a specific optimization result by ID."""

    optimization_id: str


class ListBacktestsQuery(BaseModel):
    """Query to list backtest results for a strategy."""

    strategy_id: str
    limit: int = 20
    include_failed: bool = False
