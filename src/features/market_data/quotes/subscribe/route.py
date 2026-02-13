"""API route for subscribing to a symbol."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.quotes.subscribe.command import SubscribeCommand

router = APIRouter()


class SubscribeRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ)")


class SubscribeResponse(BaseModel):
    subscription_key: str
    message: str


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_to_symbol(
    request: SubscribeRequest,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> SubscribeResponse:
    cmd = SubscribeCommand(symbol=request.symbol, exchange=request.exchange)

    try:
        result = await mediator.send(cmd)
        return SubscribeResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
