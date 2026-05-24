"""GetStrategyTrades API route — GET /{strategy_id}/trades."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.get_trades.query import (
    GetStrategyTradesQuery,
)

router = APIRouter(route_class=DishkaRoute)


@router.get("/{strategy_id}/trades")
async def get_strategy_trades(
    strategy_id: str,
    mediator: FromDishka[Mediator],
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    """Return recent completed trades for a strategy instance."""
    return await mediator.send(
        GetStrategyTradesQuery(strategy_id=strategy_id, limit=limit)
    )
