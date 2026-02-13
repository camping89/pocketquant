"""Get strategy API route."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.strategy.get_one.query import GetStrategyQuery

router = APIRouter()


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
