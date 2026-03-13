"""Get strategies API route."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.common.mediator import Mediator
from src.dependencies import get_mediator
from src.features.strategy.get_all.query import GetStrategiesQuery

router = APIRouter()


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
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> list[dict]:
    """Get all loaded strategies."""
    return await mediator.send(GetStrategiesQuery())
