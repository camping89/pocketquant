"""Get order route."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from src.common.mediator import Mediator
from src.features.trading.get_order.query import GetOrderQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/orders/{order_id}")
async def get_order(order_id: str, mediator: FromDishka[Mediator]) -> dict:
    """Get a specific order."""
    return await mediator.send(GetOrderQuery(order_id=order_id))
