"""Start subscription API route — POST /subscriptions/{sub_id}/start."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.start.command import StartStrategyCommand

router = APIRouter(route_class=DishkaRoute)


@router.post("/{sub_id}/start")
async def start_subscription(
    sub_id: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Start the strategy instance bound to this subscription."""
    await mediator.send(StartStrategyCommand(subscription_id=sub_id))
    return {"subscription_id": sub_id, "status": "started"}
