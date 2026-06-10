"""List strategy templates — GET /strategies/."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pydantic import BaseModel

from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.get_all.query import GetStrategiesQuery

router = APIRouter(route_class=DishkaRoute)


class StrategyTemplateResponse(BaseModel):
    """Strategy template entry (from STRATEGY_REGISTRY)."""

    strategy_code: str


@router.get("/", response_model=list[StrategyTemplateResponse])
async def list_strategy_templates(
    mediator: FromDishka[Mediator],
) -> list[dict]:
    """List registered strategy templates from STRATEGY_REGISTRY."""
    return await mediator.send(GetStrategiesQuery())
