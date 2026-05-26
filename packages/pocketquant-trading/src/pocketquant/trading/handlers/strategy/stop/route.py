"""Stop subscription API route — POST /subscriptions/{sub_id}/stop."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.stop.command import StopStrategyCommand

router = APIRouter(route_class=DishkaRoute)


@router.post("/{sub_id}/stop")
async def stop_subscription(
    sub_id: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Stop the strategy instance bound to this subscription."""
    await mediator.send(StopStrategyCommand(subscription_id=sub_id))
    return {"subscription_id": sub_id, "status": "stopped"}
