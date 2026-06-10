"""Get strategy template API route — GET /strategies/{strategy_code}."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.get_one.query import GetStrategyQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/{strategy_code}")
async def get_strategy_template(
    strategy_code: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Get template metadata for a registered strategy code."""
    result = await mediator.send(GetStrategyQuery(strategy_code=strategy_code))
    if not result:
        raise NotFoundError(f"Strategy template not found: {strategy_code}")
    return result
