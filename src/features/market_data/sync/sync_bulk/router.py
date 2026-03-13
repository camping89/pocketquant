"""Route for bulk symbol sync."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from src.common.mediator import Mediator
from src.features.market_data.sync.dto import SyncResponse
from src.features.market_data.sync.sync_bulk.command import BulkSyncCommand

router = APIRouter(route_class=DishkaRoute)


@router.post("/sync/bulk", response_model=list[SyncResponse])
async def sync_bulk(
    cmd: BulkSyncCommand,
    mediator: FromDishka[Mediator],
) -> list[SyncResponse]:
    return await mediator.send(cmd)
