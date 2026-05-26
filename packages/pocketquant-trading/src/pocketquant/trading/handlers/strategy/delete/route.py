"""Delete strategy template API route — DELETE /strategies/{strategy_code}."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Response
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.delete.command import DeleteStrategyCommand

router = APIRouter(route_class=DishkaRoute)


@router.delete("/{strategy_code}", status_code=204)
async def delete_strategy_by_code(
    strategy_code: str,
    mediator: FromDishka[Mediator],
) -> Response:
    """Cascade delete a strategy template: unload, cancel jobs, delete subs and backtest cache."""
    await mediator.send(DeleteStrategyCommand(strategy_id=strategy_code))
    return Response(status_code=204)
