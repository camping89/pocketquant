"""RunAllBacktests API route — POST /{strategy_id}/backtest/run-all."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.run_all_backtests.command import RunAllBacktestsCommand

router = APIRouter(route_class=DishkaRoute)


@router.post("/{strategy_id}/backtest/run-all", status_code=202)
async def run_all_backtests(
    strategy_id: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Enqueue an immediate backtest job for every subscription of the strategy."""
    return await mediator.send(RunAllBacktestsCommand(strategy_id=strategy_id))
