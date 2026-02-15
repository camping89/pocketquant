"""Load strategy API route."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.application.strategy.yaml_strategy_loader import StrategyLoader
from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.strategy.load.command import LoadStrategyCommand

router = APIRouter()


class LoadStrategyRequest(BaseModel):
    """Request to load a strategy from file path."""

    path: str = Field(..., description="Path to strategy YAML file")


@router.post("/load")
async def load_strategy(
    body: LoadStrategyRequest,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Load a strategy from YAML file."""
    path = Path(body.path)
    config = StrategyLoader.load(path)
    strategy_id = await mediator.send(LoadStrategyCommand(config=config))
    return {"strategy_id": strategy_id, "status": "loaded"}
