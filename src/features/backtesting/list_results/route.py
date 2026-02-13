"""API routes for listing backtests."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.backtesting.list_results.query import ListBacktestsQuery

router = APIRouter()


@router.get("/strategy/{strategy_id}")
async def list_backtests(
    strategy_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
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
            "strategy_id": r.strategy_id,
            "status": r.status,
            "metrics": r.metrics.to_dict(),
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat(),
            "parameters": r.parameters,
            "error_message": r.error_message,
        }
        for r in results
    ]
