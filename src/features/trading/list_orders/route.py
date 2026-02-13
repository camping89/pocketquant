"""List orders route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.trading.list_orders.query import ListOrdersQuery

router = APIRouter()


@router.get("/orders")
async def list_orders(
    mediator: Annotated[Mediator, Depends(get_mediator)]
) -> list[dict]:
    """Get all orders."""
    return await mediator.send(ListOrdersQuery())
