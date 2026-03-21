"""Start strategy API route."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.start.command import StartStrategyCommand

router = APIRouter(route_class=DishkaRoute)


@router.post("/{strategy_id}/start")
async def start_strategy(
    strategy_id: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Start a loaded strategy."""
    await mediator.send(StartStrategyCommand(strategy_id=strategy_id))
    return {"strategy_id": strategy_id, "status": "started"}
