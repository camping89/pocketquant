"""GetSubscriptionBacktest API route — GET /{strategy_id}/symbols/{sub_id}/backtest."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.get_subscription_backtest.query import (
    GetSubscriptionBacktestQuery,
)

router = APIRouter(route_class=DishkaRoute)


@router.get("/{strategy_id}/symbols/{sub_id}/backtest")
async def get_subscription_backtest(
    strategy_id: str,
    sub_id: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Return the cached backtest result for a subscription (200) or 404 if never run."""
    return await mediator.send(
        GetSubscriptionBacktestQuery(strategy_id=strategy_id, sub_id=sub_id)
    )
