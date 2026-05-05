"""Delete strategy API route — DELETE /{strategy_id}."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Response
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.delete.command import DeleteStrategyCommand

router = APIRouter(route_class=DishkaRoute)


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: str,
    mediator: FromDishka[Mediator],
) -> Response:
    """Cascade delete a strategy: unload, cancel jobs, delete subs and backtest cache."""
    await mediator.send(DeleteStrategyCommand(strategy_id=strategy_id))
    return Response(status_code=204)
