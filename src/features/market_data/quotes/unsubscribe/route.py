"""API route for unsubscribing from a symbol."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.common.mediator import Mediator
from src.dependencies import get_mediator
from src.features.market_data.quotes.unsubscribe.command import UnsubscribeCommand

router = APIRouter()


class UnsubscribeRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ)")


@router.post("/unsubscribe")
async def unsubscribe_from_symbol(
    request: UnsubscribeRequest,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    cmd = UnsubscribeCommand(symbol=request.symbol, exchange=request.exchange)
    return await mediator.send(cmd)
