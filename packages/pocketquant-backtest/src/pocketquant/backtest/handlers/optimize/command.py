from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class RunOptimizationCommand(BaseModel):
    """Command to run grid optimization across parameter combinations.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(..., description="Composite symbol (e.g. BTCUSDT:BINANCE)")
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
