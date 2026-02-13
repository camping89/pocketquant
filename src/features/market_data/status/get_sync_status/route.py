"""Route for getting all sync statuses."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.status.get_sync_status.query import GetSyncStatusQuery

router = APIRouter()


@router.get("/sync-status")
async def get_sync_statuses(
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> list[dict]:
    query = GetSyncStatusQuery()
    statuses = await mediator.send(query)

    return [
        {
            "symbol": s.symbol,
            "exchange": s.exchange,
            "interval": s.interval,
            "status": s.status,
            "bar_count": s.bar_count,
            "last_sync_at": s.last_sync_at,
            "last_bar_at": s.last_bar_at,
            "error_message": s.error_message,
        }
        for s in statuses
    ]
