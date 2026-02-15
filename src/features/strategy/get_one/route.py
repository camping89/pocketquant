"""Get strategy API route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.exceptions import NotFoundError
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
        raise NotFoundError(f"Strategy not found: {strategy_id}")

    return result
