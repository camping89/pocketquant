"""API routes for listing backtests."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.backtest.handlers.list_results.query import ListBacktestsQuery
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.get("/strategy/{strategy_id}")
async def list_backtests(
    strategy_id: str,
    mediator: FromDishka[Mediator],
    limit: int = 20,
    include_failed: bool = False,
) -> list[dict]:
    """List backtest results for a strategy.

    Returns summary information without full equity curves.
    """
    query = ListBacktestsQuery(
        strategy_id=strategy_id,
        limit=limit,
        include_failed=include_failed,
    )
    results = await mediator.send(query)

    return [
        {
            "id": r.id,
            "strategy_code": r.strategy_code,
            "status": r.status,
            "metrics": r.metrics.to_dict(),
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat(),
            "parameters": r.parameters,
            "error_message": r.error_message,
        }
        for r in results
    ]
