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


class TradeResponse(BaseModel):
    """Single trade from backtest."""

    side: str
    price: float
    quantity: float
    pnl: float
    commission: float
    timestamp: datetime


class RunBacktestResponse(BaseModel):
    """Response after submitting backtest."""

    run_id: str
    status: str
    metrics: BacktestMetricsResponse | None = None
    trades: list[TradeResponse] = []


@router.post("/run", response_model=RunBacktestResponse)
async def run_backtest(
    cmd: RunBacktestCommand,
    mediator: FromDishka[Mediator],
) -> dict:
    """Execute a single backtest run.

    Runs the specified strategy over historical data and returns performance metrics.
    """
    result = await mediator.send(cmd)

    trades = [
        {
            "side": t.side,
            "price": t.price,
            "quantity": t.quantity,
            "pnl": t.pnl,
            "commission": t.commission,
            "timestamp": t.timestamp,
        }
        for t in result.trades
    ] if result.status == "completed" else []

    return {
        "run_id": result.id,
        "status": result.status,
        "metrics": result.metrics.to_dict() if result.status == "completed" else None,
        "trades": trades,
    }
