"""Get position route."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from src.common.mediator import Mediator
from src.features.trading.get_position.query import GetPositionQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/positions/{strategy_id}")
async def get_position(
    strategy_id: str, mediator: FromDishka[Mediator]
) -> dict:
    """Get position for a specific strategy."""
    return await mediator.send(GetPositionQuery(strategy_id=strategy_id))
