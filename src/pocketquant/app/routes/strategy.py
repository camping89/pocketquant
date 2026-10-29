from typing import Literal

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.engine.live.live_metrics_query_service import LiveMetricsQueryService
from pocketquant.engine.strategy.strategy_command_service import StrategyCommandService
from pocketquant.engine.strategy.strategy_query_service import StrategyQueryService


class CreateSubscriptionBody(BaseModel):
    symbol: str
    interval: str
    broker: Literal["paper", "exness"] = "paper"


# strategy_router  — /strategies prefix

strategy_router = APIRouter(prefix="/strategies", tags=["strategies"], route_class=DishkaRoute)


class StrategyTemplateResponse(BaseModel):
    strategy_code: str


@strategy_router.get("/", response_model=list[StrategyTemplateResponse])
async def list_strategy_templates(
    query_svc: FromDishka[StrategyQueryService],
) -> list[dict]:
    return await query_svc.get_all()


@strategy_router.get("/{strategy_code}")
async def get_strategy_template(
    strategy_code: str,
    query_svc: FromDishka[StrategyQueryService],
) -> dict:
    result = await query_svc.get_one(strategy_code)
    if not result:
        raise NotFoundError(f"Strategy template not found: {strategy_code}")
    return result


@strategy_router.post("/{strategy_code}/subscriptions", status_code=201)
async def create_subscription(
    strategy_code: str,
    body: CreateSubscriptionBody,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    return await cmd_svc.add_symbol(strategy_code, body.symbol, body.interval, body.broker)


# subscription_router  — /subscriptions prefix

subscription_router = APIRouter(
    prefix="/subscriptions", tags=["subscriptions"], route_class=DishkaRoute
)


@subscription_router.get("/")
async def list_subscriptions(
    query_svc: FromDishka[StrategyQueryService],
    strategy_code: str | None = None,
) -> list:
    return await query_svc.list_symbols(strategy_code)


@subscription_router.post("/{sub_id}/start")
async def start_subscription(
    sub_id: str,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    await cmd_svc.start(sub_id)
    return {"subscription_id": sub_id, "status": "started"}


@subscription_router.post("/{sub_id}/stop")
async def stop_subscription(
    sub_id: str,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    await cmd_svc.stop(sub_id)
    return {"subscription_id": sub_id, "status": "stopped"}


@subscription_router.get("/{sub_id}/positions")
async def get_subscription_positions(
    sub_id: str,
    query_svc: FromDishka[StrategyQueryService],
) -> list[dict]:
    return await query_svc.get_positions(sub_id)


@subscription_router.get("/{sub_id}/trades")
async def get_subscription_trades(
    sub_id: str,
    query_svc: FromDishka[StrategyQueryService],
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    return await query_svc.get_trades(sub_id, limit)


@subscription_router.get("/{sub_id}/metrics")
async def get_subscription_metrics(
    sub_id: str,
    metrics_svc: FromDishka[LiveMetricsQueryService],
) -> dict:
    return await metrics_svc.get_metrics(sub_id)


@subscription_router.delete("/{sub_id}", status_code=204)
async def remove_subscription(
    sub_id: str,
    cmd_svc: FromDishka[StrategyCommandService],
) -> Response:
    await cmd_svc.remove_symbol(sub_id)
    return Response(status_code=204)
