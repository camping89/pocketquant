"""Load strategy API route."""

from pathlib import Path

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.app_services.yaml_strategy_loader import StrategyLoader
from pocketquant.trading.handlers.strategy.load.command import LoadStrategyCommand
from pydantic import BaseModel, Field

router = APIRouter(route_class=DishkaRoute)


class LoadStrategyRequest(BaseModel):
    """Request to load a strategy from file path."""

    path: str = Field(..., description="Path to strategy YAML file")


@router.post("/load")
async def load_strategy(
    body: LoadStrategyRequest,
    mediator: FromDishka[Mediator],
) -> dict:
    """Load a strategy from YAML file."""
    path = Path(body.path)
    config = StrategyLoader.load(path)
    strategy_id = await mediator.send(LoadStrategyCommand(config=config))
    return {"strategy_id": strategy_id, "status": "loaded"}
