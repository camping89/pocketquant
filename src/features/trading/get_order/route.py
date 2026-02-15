"""Get order route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.trading.get_order.query import GetOrderQuery

router = APIRouter()


@router.get("/orders/{order_id}")
async def get_order(order_id: str, mediator: Annotated[Mediator, Depends(get_mediator)]) -> dict:
    """Get a specific order."""
    return await mediator.send(GetOrderQuery(order_id=order_id))
