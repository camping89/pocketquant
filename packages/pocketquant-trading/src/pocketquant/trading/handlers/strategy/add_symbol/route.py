"""AddSymbol API route — POST /{strategy_id}/symbols."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.add_symbol.command import AddSymbolCommand
from pydantic import BaseModel

router = APIRouter(route_class=DishkaRoute)


class AddSymbolBody(BaseModel):
    """Request body for adding a symbol subscription."""

    symbol: str
    exchange: str
    interval: str


@router.post("/{strategy_id}/symbols", status_code=201)
async def add_symbol(
    strategy_id: str,
    body: AddSymbolBody,
    mediator: FromDishka[Mediator],
) -> dict:
    """Subscribe a loaded strategy to a (symbol, exchange, interval) tuple."""
    return await mediator.send(
        AddSymbolCommand(
            strategy_id=strategy_id,
            symbol=body.symbol,
            exchange=body.exchange,
            interval=body.interval,
        )
    )
