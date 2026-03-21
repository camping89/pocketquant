"""Get strategy API route."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.get_one.query import GetStrategyQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Get a specific strategy by ID."""
    result = await mediator.send(GetStrategyQuery(strategy_id=strategy_id))

    if not result:
        raise NotFoundError(f"Strategy not found: {strategy_id}")

    return result
