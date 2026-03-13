"""API routes for getting backtest results."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.exceptions import NotFoundError
from src.common.mediator import Mediator
from src.dependencies import get_mediator
from src.features.backtesting.get_result.query import GetBacktestQuery

router = APIRouter()


@router.get("/{run_id}")
async def get_backtest(
    run_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Get a specific backtest result by ID.

    Returns full result including equity curve and trade history.
    """
    query = GetBacktestQuery(run_id=run_id)
    result = await mediator.send(query)

    if not result:
        raise NotFoundError(f"Backtest not found: {run_id}")

    return result.to_dict()


@router.get("/{run_id}/equity")
async def get_backtest_equity(
    run_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Get equity curve data for a backtest.

    Returns only the equity curve for charting purposes.
    """
    query = GetBacktestQuery(run_id=run_id)
    result = await mediator.send(query)

    if not result:
        raise NotFoundError(f"Backtest not found: {run_id}")

    return {
        "run_id": result.id,
        "equity_curve": [
            {"timestamp": p.timestamp.isoformat(), "equity": p.equity, "drawdown": p.drawdown}
            for p in result.equity_curve
        ],
    }
