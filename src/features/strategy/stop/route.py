"""Stop strategy API route."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.strategy.stop.command import StopStrategyCommand

router = APIRouter()


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
