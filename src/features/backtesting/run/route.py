"""API routes for running a backtest."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.backtesting.run.command import RunBacktestCommand

router = APIRouter()


class BacktestMetricsResponse(BaseModel):
    """Backtest performance metrics."""

    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_commission: float


class RunBacktestResponse(BaseModel):
    """Response after submitting backtest."""

    run_id: str
    status: str
    metrics: BacktestMetricsResponse | None = None


@router.post("/run", response_model=RunBacktestResponse)
async def run_backtest(
    cmd: RunBacktestCommand,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Execute a single backtest run.

    Runs the specified strategy over historical data and returns performance metrics.
    """
    result = await mediator.send(cmd)

    return {
        "run_id": result.id,
        "status": result.status,
        "metrics": result.metrics.to_dict() if result.status == "completed" else None,
    }
