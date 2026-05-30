"""Get order route."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.trading.get_order.query import GetOrderQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/orders/{order_id}")
async def get_order(order_id: str, mediator: FromDishka[Mediator]) -> dict:
    return await mediator.send(GetOrderQuery(order_id=order_id))
