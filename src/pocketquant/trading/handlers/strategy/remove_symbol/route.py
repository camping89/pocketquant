"""RemoveSubscription API route — DELETE /subscriptions/{sub_id}."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Response

from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.remove_symbol.command import RemoveSymbolCommand

router = APIRouter(route_class=DishkaRoute)


@router.delete("/{sub_id}", status_code=204)
async def remove_subscription(
    sub_id: str,
    mediator: FromDishka[Mediator],
) -> Response:
    """Delete a subscription and its cached backtest result."""
    await mediator.send(RemoveSymbolCommand(sub_id=sub_id))
    return Response(status_code=204)
