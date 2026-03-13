"""Route for bulk symbol sync."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.dependencies import get_mediator
from src.features.market_data.sync.dto import SyncResponse
from src.features.market_data.sync.sync_bulk.command import BulkSyncCommand

router = APIRouter()


@router.post("/sync/bulk", response_model=list[SyncResponse])
async def sync_bulk(
    cmd: BulkSyncCommand,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> list[SyncResponse]:
    return await mediator.send(cmd)
