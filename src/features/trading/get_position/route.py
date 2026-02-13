"""Get position route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.trading.get_position.query import GetPositionQuery

router = APIRouter()


@router.get("/positions/{strategy_id}")
async def get_position(
    strategy_id: str, mediator: Annotated[Mediator, Depends(get_mediator)]
) -> dict:
    """Get position for a specific strategy."""
    return await mediator.send(GetPositionQuery(strategy_id=strategy_id))
