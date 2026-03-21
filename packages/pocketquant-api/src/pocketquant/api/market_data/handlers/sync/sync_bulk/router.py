"""Route for bulk symbol sync."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.api.market_data.handlers.sync.dto import SyncResponse
from pocketquant.api.market_data.handlers.sync.sync_bulk.command import BulkSyncCommand
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.post("/sync/bulk", response_model=list[SyncResponse])
async def sync_bulk(
    cmd: BulkSyncCommand,
    mediator: FromDishka[Mediator],
) -> list[SyncResponse]:
    return await mediator.send(cmd)
