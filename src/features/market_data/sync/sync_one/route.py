"""Route for syncing a single symbol."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from src.common.logging import get_logger
from src.common.mediator import Mediator
from src.dependencies import get_mediator
from src.features.market_data.sync.dto import SyncResponse
from src.features.market_data.sync.sync_one.command import SyncSymbolCommand

logger = get_logger(__name__)

router = APIRouter()


@router.post("/sync", response_model=SyncResponse)
async def sync_symbol(
    cmd: SyncSymbolCommand,
    mediator: Annotated[Mediator, Depends(get_mediator)],
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
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    async def run_sync() -> None:
        await mediator.send(cmd)

    background_tasks.add_task(run_sync)

    return {
        "status": "accepted",
        "message": f"Sync started for {cmd.symbol}:{cmd.exchange}",
    }
