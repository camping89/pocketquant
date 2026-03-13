"""Stop strategy API route."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from src.common.mediator import Mediator
from src.features.strategy.stop.command import StopStrategyCommand

router = APIRouter(route_class=DishkaRoute)


@router.post("/{strategy_id}/stop")
async def stop_strategy(
    strategy_id: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Stop a running strategy."""
    await mediator.send(StopStrategyCommand(strategy_id=strategy_id))
    return {"strategy_id": strategy_id, "status": "stopped"}
