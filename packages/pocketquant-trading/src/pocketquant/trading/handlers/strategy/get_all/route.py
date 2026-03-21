"""Get strategies API route."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.get_all.query import GetStrategiesQuery
from pydantic import BaseModel

router = APIRouter(route_class=DishkaRoute)


class StrategyResponse(BaseModel):
    """Strategy information response."""

    id: str
    name: str
    symbol: str
    exchange: str
    interval: str
    broker: str
    is_running: bool


@router.get("/", response_model=list[StrategyResponse])
async def list_strategies(
    mediator: FromDishka[Mediator],
) -> list[dict]:
    """Get all loaded strategies."""
    return await mediator.send(GetStrategiesQuery())
