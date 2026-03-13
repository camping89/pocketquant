"""List positions route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.dependencies import get_mediator
from src.features.trading.list_positions.query import ListPositionsQuery

router = APIRouter()


@router.get("/positions")
async def list_positions(mediator: Annotated[Mediator, Depends(get_mediator)]) -> list[dict]:
    """Get all open positions."""
    return await mediator.send(ListPositionsQuery())
