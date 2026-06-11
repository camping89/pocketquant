"""Sync routes — single-symbol and bulk OHLCV sync endpoints."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks

from pocketquant.core.common.logging import get_logger
from pocketquant.engine.market_data.sync_service import (
    BulkSyncCommand,
    SyncResponse,
    SyncService,
    SyncSymbolCommand,
)

logger = get_logger(__name__)

router = APIRouter(route_class=DishkaRoute)


@router.post("/sync", response_model=SyncResponse)
async def sync_symbol(
    cmd: SyncSymbolCommand,
    sync_service: FromDishka[SyncService],
) -> SyncResponse:
    """Sync historical OHLCV data. ``symbol`` in body is composite ``{code}:{exchange}``."""
    logger.info(
        "api.sync_requested",
        symbol=cmd.symbol,
        interval=cmd.interval.value,
    )
    return await sync_service.sync_one(cmd)


@router.post("/sync/background", response_model=dict)
async def sync_symbol_background(
    cmd: SyncSymbolCommand,
    background_tasks: BackgroundTasks,
    sync_service: FromDishka[SyncService],
) -> dict:
    async def run_sync() -> None:
        await sync_service.sync_one(cmd)

    background_tasks.add_task(run_sync)

    return {
        "status": "accepted",
        "message": f"Sync started for {cmd.symbol}",
    }


@router.post("/sync/bulk", response_model=list[SyncResponse])
async def sync_bulk(
    cmd: BulkSyncCommand,
    sync_service: FromDishka[SyncService],
) -> list[SyncResponse]:
    return await sync_service.sync_bulk(cmd)
