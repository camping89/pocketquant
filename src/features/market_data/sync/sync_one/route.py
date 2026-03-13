"""Route for syncing a single symbol."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks

from src.common.logging import get_logger
from src.common.mediator import Mediator
from src.features.market_data.sync.dto import SyncResponse
from src.features.market_data.sync.sync_one.command import SyncSymbolCommand

logger = get_logger(__name__)

router = APIRouter(route_class=DishkaRoute)


@router.post("/sync", response_model=SyncResponse)
async def sync_symbol(
    cmd: SyncSymbolCommand,
    mediator: FromDishka[Mediator],
) -> SyncResponse:
    logger.info(
        "api.sync_requested",
        symbol=cmd.symbol,
        exchange=cmd.exchange,
        interval=cmd.interval.value,
    )
    return await mediator.send(cmd)


@router.post("/sync/background", response_model=dict)
async def sync_symbol_background(
    cmd: SyncSymbolCommand,
    background_tasks: BackgroundTasks,
    mediator: FromDishka[Mediator],
) -> dict:
    async def run_sync() -> None:
        await mediator.send(cmd)

    background_tasks.add_task(run_sync)

    return {
        "status": "accepted",
        "message": f"Sync started for {cmd.symbol}:{cmd.exchange}",
    }
