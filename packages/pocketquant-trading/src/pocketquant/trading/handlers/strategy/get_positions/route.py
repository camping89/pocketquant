"""GetStrategyPositions API route — GET /{strategy_id}/positions."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.get_positions.query import (
    GetStrategyPositionsQuery,
)

router = APIRouter(route_class=DishkaRoute)


@router.get("/{strategy_id}/positions")
async def get_strategy_positions(
    strategy_id: str,
    mediator: FromDishka[Mediator],
) -> list[dict]:
    """Return open positions for a strategy instance (per-subscription id)."""
    return await mediator.send(GetStrategyPositionsQuery(strategy_id=strategy_id))
