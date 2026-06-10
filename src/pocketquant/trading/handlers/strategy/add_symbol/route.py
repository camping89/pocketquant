"""CreateSubscription API route — POST /strategies/{strategy_code}/subscriptions."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pydantic import BaseModel

from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.add_symbol.command import AddSymbolCommand

router = APIRouter(route_class=DishkaRoute)


class CreateSubscriptionBody(BaseModel):
    """Request body for creating a subscription under a strategy template.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    symbol: str
    interval: str


@router.post("/{strategy_code}/subscriptions", status_code=201)
async def create_subscription(
    strategy_code: str,
    body: CreateSubscriptionBody,
    mediator: FromDishka[Mediator],
) -> dict:
    """Create a subscription that binds a strategy template to (symbol, interval).

    ``symbol`` must be composite ``{code}:{exchange}``.
    """
    return await mediator.send(
        AddSymbolCommand(
            strategy_id=strategy_code,
            symbol=body.symbol,
            interval=body.interval,
        )
    )
