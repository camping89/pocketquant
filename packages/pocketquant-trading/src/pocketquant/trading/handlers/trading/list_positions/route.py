"""List positions route."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.trading.list_positions.query import ListPositionsQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/positions")
async def list_positions(mediator: FromDishka[Mediator]) -> list[dict]:
    """Get all open positions."""
    return await mediator.send(ListPositionsQuery())
