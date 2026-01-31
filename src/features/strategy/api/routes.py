"""Strategy API routes."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.strategy.handlers import (
    GetStrategiesQuery,
    GetStrategyQuery,
    LoadStrategyCommand,
    StartStrategyCommand,
    StopStrategyCommand,
)
from src.features.strategy.loader import StrategyLoader, StrategyLoaderError

router = APIRouter(prefix="/strategies", tags=["strategies"])


class LoadStrategyRequest(BaseModel):
    """Request to load a strategy from file path."""

    path: str


class StrategyResponse(BaseModel):
    """Strategy information response."""

    id: str
    name: str
    symbol: str
    exchange: str
    interval: str
    broker: str
    is_running: bool


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> list[dict]:
    """Get all loaded strategies."""
    return await mediator.send(GetStrategiesQuery())


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Get a specific strategy by ID."""
    result = await mediator.send(GetStrategyQuery(strategy_id=strategy_id))

    if not result:
        raise HTTPException(status_code=404, detail=f"Strategy not found: {strategy_id}")

    return result


@router.post("/load")
async def load_strategy(
    body: LoadStrategyRequest,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Load a strategy from YAML file."""
    try:
        path = Path(body.path)
        config = StrategyLoader.load(path)

        strategy_id = await mediator.send(LoadStrategyCommand(config=config))

        return {"strategy_id": strategy_id, "status": "loaded"}

    except StrategyLoaderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{strategy_id}/start")
async def start_strategy(
    strategy_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Start a loaded strategy."""
    try:
        await mediator.send(StartStrategyCommand(strategy_id=strategy_id))
        return {"strategy_id": strategy_id, "status": "started"}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{strategy_id}/stop")
async def stop_strategy(
    strategy_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Stop a running strategy."""
    try:
        await mediator.send(StopStrategyCommand(strategy_id=strategy_id))
        return {"strategy_id": strategy_id, "status": "stopped"}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
