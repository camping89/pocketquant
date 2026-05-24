"""CQRS command for running a backtest."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class RunBacktestCommand(BaseModel):
    """Command to execute a single backtest run.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(..., description="Composite symbol (e.g. BTCUSDT:BINANCE)")
    interval: str = Field(..., description="Bar interval (e.g. 5m, 1h)")
    start_date: date = Field(..., description="Backtest start date")
    end_date: date = Field(..., description="Backtest end date")
    initial_capital: float = Field(default=10_000.0, ge=100, description="Starting capital")
    slippage_bps: float = Field(default=10.0, ge=0, description="Slippage in basis points")
    commission_bps: float = Field(default=10.0, ge=0, description="Commission in basis points")
    parameters: dict[str, Any] | None = Field(default=None, description="Strategy parameters")
