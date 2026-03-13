"""API route for subscribing to a symbol."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.common.mediator import Mediator
from src.features.market_data.quotes.subscribe.command import SubscribeCommand

router = APIRouter(route_class=DishkaRoute)


class SubscribeRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ)")


class SubscribeResponse(BaseModel):
    subscription_key: str
    message: str


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_to_symbol(
    request: SubscribeRequest,
    mediator: FromDishka[Mediator],
) -> SubscribeResponse:
    cmd = SubscribeCommand(symbol=request.symbol, exchange=request.exchange)
    result = await mediator.send(cmd)
    return SubscribeResponse(**result)
