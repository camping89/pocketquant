"""API route for subscribing to a symbol."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.api.market_data.handlers.quotes.subscribe.command import SubscribeCommand
from pocketquant.core.common.mediator import Mediator
from pydantic import BaseModel, Field

router = APIRouter(route_class=DishkaRoute)


class SubscribeRequest(BaseModel):
    symbol: str = Field(..., description="Composite symbol (e.g., BTCUSDT:BINANCE)")


class SubscribeResponse(BaseModel):
    subscription_key: str
    message: str


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_to_symbol(
    request: SubscribeRequest,
    mediator: FromDishka[Mediator],
) -> SubscribeResponse:
    cmd = SubscribeCommand(symbol=request.symbol)
    result = await mediator.send(cmd)
    return SubscribeResponse(**result)
