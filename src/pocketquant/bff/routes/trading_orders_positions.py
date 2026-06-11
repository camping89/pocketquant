"""Trading orders + positions routes — live in-RAM engine state.

These routes depend on OrderPositionQueryService which requires
OrderAppService / PositionAppService (live in-RAM engine state).
They are mounted in both bff and app main_extensions but the service
is only registered in the app DI container — bff will return 500 if
called (same runtime behaviour as the previous handler exclusion).
"""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.engine.orders_positions_service import (
    GetOrderQuery,
    GetPositionQuery,
    ListOrdersQuery,
    ListPositionsQuery,
    OrderPositionQueryService,
)

trading_router = APIRouter(prefix="/trading", tags=["trading"], route_class=DishkaRoute)


@trading_router.get("/orders")
async def list_orders(svc: FromDishka[OrderPositionQueryService]) -> list[dict]:
    return await svc.list_orders(ListOrdersQuery())


@trading_router.get("/orders/{order_id}")
async def get_order(order_id: str, svc: FromDishka[OrderPositionQueryService]) -> dict:
    return await svc.get_order(GetOrderQuery(order_id=order_id))


@trading_router.get("/positions")
async def list_positions(svc: FromDishka[OrderPositionQueryService]) -> list[dict]:
    return await svc.list_positions(ListPositionsQuery())


@trading_router.get("/positions/{strategy_id}")
async def get_position(strategy_id: str, svc: FromDishka[OrderPositionQueryService]) -> dict:
    return await svc.get_position(GetPositionQuery(strategy_id=strategy_id))
