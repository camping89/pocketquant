"""List orders route."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from src.common.mediator import Mediator
from src.features.trading.list_orders.query import ListOrdersQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/orders")
async def list_orders(mediator: FromDishka[Mediator]) -> list[dict]:
    """Get all orders."""
    return await mediator.send(ListOrdersQuery())
