"""GetSubscriptionPositions API route — GET /subscriptions/{sub_id}/positions."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.get_positions.query import (
    GetStrategyPositionsQuery,
)

router = APIRouter(route_class=DishkaRoute)


@router.get("/{sub_id}/positions")
async def get_subscription_positions(
    sub_id: str,
    mediator: FromDishka[Mediator],
) -> list[dict]:
    """Return open positions for a subscription's strategy instance."""
    return await mediator.send(GetStrategyPositionsQuery(subscription_id=sub_id))
