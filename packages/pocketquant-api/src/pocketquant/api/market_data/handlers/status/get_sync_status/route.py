"""Route for getting all sync statuses."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.api.market_data.handlers.status.get_sync_status.query import GetSyncStatusQuery
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.get("/sync-status")
async def get_sync_statuses(
    mediator: FromDishka[Mediator],
) -> list[dict]:
    query = GetSyncStatusQuery()
    statuses = await mediator.send(query)

    return [
        {
            "symbol": s.symbol,
            "interval": s.interval,
            "status": s.status,
            "bar_count": s.bar_count,
            "last_sync_at": s.last_sync_at,
            "last_bar_at": s.last_bar_at,
            "error_message": s.error_message,
            "consecutive_empty_fetches": s.consecutive_empty_fetches,
            "is_stuck": s.is_stuck,
        }
        for s in statuses
    ]
