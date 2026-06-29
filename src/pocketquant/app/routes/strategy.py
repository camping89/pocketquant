"""Strategy + subscription API routes.

Two top-level routers:

* ``strategy_router``      (prefix ``/strategies``)    — template-scoped operations
* ``subscription_router``  (prefix ``/subscriptions``) — subscription-instance operations
"""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.engine.strategy_command_service import (
    AddSymbolCommand,
    DeleteStrategyCommand,
    RemoveSymbolCommand,
    StartStrategyCommand,
    StopStrategyCommand,
    StrategyCommandService,
)
from pocketquant.engine.strategy_query_service import (
    GetStrategiesQuery,
    GetStrategyPositionsQuery,
    GetStrategyQuery,
    GetStrategyTradesQuery,
    ListSymbolsQuery,
    StrategyQueryService,
)


class CreateSubscriptionBody(BaseModel):
    """Request body for creating a subscription under a strategy template.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    symbol: str
    interval: str


# strategy_router  — /strategies prefix

strategy_router = APIRouter(prefix="/strategies", tags=["strategies"], route_class=DishkaRoute)


class StrategyTemplateResponse(BaseModel):
    strategy_code: str


@strategy_router.get("/", response_model=list[StrategyTemplateResponse])
async def list_strategy_templates(
    query_svc: FromDishka[StrategyQueryService],
) -> list[dict]:
    return await query_svc.get_all(GetStrategiesQuery())


@strategy_router.get("/{strategy_code}")
async def get_strategy_template(
    strategy_code: str,
    query_svc: FromDishka[StrategyQueryService],
) -> dict:
    result = await query_svc.get_one(GetStrategyQuery(strategy_code=strategy_code))
    if not result:
        raise NotFoundError(f"Strategy template not found: {strategy_code}")
    return result


@strategy_router.post("/{strategy_code}/subscriptions", status_code=201)
async def create_subscription(
    strategy_code: str,
    body: CreateSubscriptionBody,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    """Create a subscription that binds a strategy template to (symbol, interval).

    ``symbol`` must be composite ``{code}:{exchange}``.
    """
    return await cmd_svc.add_symbol(
        AddSymbolCommand(
            strategy_id=strategy_code,
            symbol=body.symbol,
            interval=body.interval,
        )
    )


@strategy_router.delete("/{strategy_code}", status_code=204)
async def delete_strategy_by_code(
    strategy_code: str,
    cmd_svc: FromDishka[StrategyCommandService],
) -> Response:
    await cmd_svc.delete_strategy(DeleteStrategyCommand(strategy_id=strategy_code))
    return Response(status_code=204)


# subscription_router  — /subscriptions prefix

subscription_router = APIRouter(
    prefix="/subscriptions", tags=["subscriptions"], route_class=DishkaRoute
)


@subscription_router.get("/")
async def list_subscriptions(
    query_svc: FromDishka[StrategyQueryService],
    strategy_code: str | None = None,
) -> list:
    return await query_svc.list_symbols(ListSymbolsQuery(strategy_code=strategy_code))


@subscription_router.post("/{sub_id}/start")
async def start_subscription(
    sub_id: str,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    await cmd_svc.start(StartStrategyCommand(subscription_id=sub_id))
    return {"subscription_id": sub_id, "status": "started"}


@subscription_router.post("/{sub_id}/stop")
async def stop_subscription(
    sub_id: str,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    await cmd_svc.stop(StopStrategyCommand(subscription_id=sub_id))
    return {"subscription_id": sub_id, "status": "stopped"}


@subscription_router.get("/{sub_id}/positions")
async def get_subscription_positions(
    sub_id: str,
    query_svc: FromDishka[StrategyQueryService],
) -> list[dict]:
    return await query_svc.get_positions(GetStrategyPositionsQuery(subscription_id=sub_id))


@subscription_router.get("/{sub_id}/trades")
async def get_subscription_trades(
    sub_id: str,
    query_svc: FromDishka[StrategyQueryService],
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    return await query_svc.get_trades(GetStrategyTradesQuery(subscription_id=sub_id, limit=limit))


@subscription_router.delete("/{sub_id}", status_code=204)
async def remove_subscription(
    sub_id: str,
    cmd_svc: FromDishka[StrategyCommandService],
) -> Response:
    await cmd_svc.remove_symbol(RemoveSymbolCommand(sub_id=sub_id))
    return Response(status_code=204)
