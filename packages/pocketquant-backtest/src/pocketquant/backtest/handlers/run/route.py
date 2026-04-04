"""API routes for running a backtest."""

from datetime import datetime

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.backtest.handlers.run.command import RunBacktestCommand
from pocketquant.core.common.mediator import Mediator
from pydantic import BaseModel

router = APIRouter(route_class=DishkaRoute)


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


class PositionResponse(BaseModel):
    """Paired entry+exit position from backtest."""

    entry_price: float
    entry_time: datetime
    exit_price: float | None = None
    exit_time: datetime | None = None
    quantity: float
    sl_price: float | None = None
    tp_price: float | None = None
    pnl: float
    commission: float


class RunBacktestResponse(BaseModel):
    """Response after submitting backtest."""

    run_id: str
    status: str
    metrics: BacktestMetricsResponse | None = None
    positions: list[PositionResponse] = []


@router.post("/run", response_model=RunBacktestResponse)
async def run_backtest(
    cmd: RunBacktestCommand,
    mediator: FromDishka[Mediator],
) -> dict:
    """Execute a single backtest run.

    Runs the specified strategy over historical data and returns performance metrics.
    """
    result = await mediator.send(cmd)

    positions = [
        {
            "entry_price": p.entry_price,
            "entry_time": p.entry_time,
            "exit_price": p.exit_price,
            "exit_time": p.exit_time,
            "quantity": p.quantity,
            "sl_price": p.sl_price,
            "tp_price": p.tp_price,
            "pnl": p.pnl,
            "commission": p.commission,
        }
        for p in result.positions
    ] if result.status == "completed" else []

    return {
        "run_id": result.id,
        "status": result.status,
        "metrics": result.metrics.to_dict() if result.status == "completed" else None,
        "positions": positions,
    }
