"""Get position route."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.trading.get_position.query import GetPositionQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/positions/{strategy_id}")
async def get_position(strategy_id: str, mediator: FromDishka[Mediator]) -> dict:
    return await mediator.send(GetPositionQuery(strategy_id=strategy_id))
