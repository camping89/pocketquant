"""Start strategy API route."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.strategy.start.command import StartStrategyCommand

router = APIRouter()


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
