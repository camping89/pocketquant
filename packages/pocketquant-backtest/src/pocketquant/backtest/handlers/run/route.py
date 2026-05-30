from datetime import datetime

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.backtest.handlers.run.command import RunBacktestCommand
from pocketquant.backtest.persistence.backtest_trade_repository import BacktestTradeRepository
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
    """Paired entry+exit position from backtest (closed) or open lot snapshot."""

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
    trade_repo: FromDishka[BacktestTradeRepository],
) -> dict:
    """Execute a single backtest run.

    Returns metrics + a unified positions list combining closed round-trip
    Trades (from ``backtest_trades``) and still-open lots (from the run doc's
    ``open_positions``). The unified shape preserves backward compatibility for
    existing FE consumers; the downstream backtest-analysis-panel plan will
    rewire to consume the new collections directly.
    """
    result = await mediator.send(cmd)

    positions: list[dict] = []
    if result.status == "completed":
        closed = await trade_repo.list_by_run(result.id)
        for t in closed:
            positions.append(
                {
                    "entry_price": t.entry_price,
                    "entry_time": t.entry_time,
                    "exit_price": t.exit_price,
                    "exit_time": t.exit_time,
                    "quantity": t.quantity,
                    "sl_price": t.sl_price,
                    "tp_price": t.tp_price,
                    "pnl": t.pnl,
                    "commission": t.commission,
                }
            )
        for ol in result.open_positions:
            positions.append(
                {
                    "entry_price": ol.entry_price,
                    "entry_time": ol.entry_time,
                    "exit_price": None,
                    "exit_time": None,
                    "quantity": ol.quantity,
                    "sl_price": ol.sl_price,
                    "tp_price": ol.tp_price,
                    "pnl": 0.0,
                    "commission": ol.entry_commission_portion,
                }
            )

    return {
        "run_id": result.id,
        "status": result.status,
        "metrics": result.metrics.to_dict() if result.status == "completed" else None,
        "positions": positions,
    }
