"""RunAllBacktests API route — POST /strategies/{strategy_code}/run-all-backtests."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.backtest.handlers.run_all_backtests.command import RunAllBacktestsCommand
from pocketquant.core.common.mediator import Mediator

router = APIRouter(prefix="/strategies", tags=["strategies"], route_class=DishkaRoute)


@router.post("/{strategy_code}/run-all-backtests", status_code=202)
async def run_all_backtests(
    strategy_code: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Enqueue an immediate backtest job for every subscription of the strategy template."""
    return await mediator.send(RunAllBacktestsCommand(strategy_id=strategy_code))
