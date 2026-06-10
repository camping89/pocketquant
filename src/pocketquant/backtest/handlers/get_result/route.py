from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.backtest.handlers.get_result.query import GetBacktestQuery
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.get("/{run_id}")
async def get_backtest(
    run_id: str,
    mediator: FromDishka[Mediator],
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
    mediator: FromDishka[Mediator],
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
