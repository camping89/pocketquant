"""API route for unsubscribing from a symbol."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.api.market_data.handlers.quotes.unsubscribe.command import UnsubscribeCommand
from pocketquant.core.common.mediator import Mediator
from pydantic import BaseModel, Field

router = APIRouter(route_class=DishkaRoute)


class UnsubscribeRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ)")


@router.post("/unsubscribe")
async def unsubscribe_from_symbol(
    request: UnsubscribeRequest,
    mediator: FromDishka[Mediator],
) -> dict:
    cmd = UnsubscribeCommand(symbol=request.symbol, exchange=request.exchange)
    return await mediator.send(cmd)
