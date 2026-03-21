"""Route for getting sync status for a specific symbol."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from pocketquant.api.market_data.handlers.status.get_symbol_sync_status.query import (
    GetSymbolSyncStatusQuery,
)
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.shared.value_objects import Interval

router = APIRouter(route_class=DishkaRoute)


@router.get("/sync-status/{exchange}/{symbol}")
async def get_symbol_sync_status(
    exchange: str,
    symbol: str,
    mediator: FromDishka[Mediator],
    interval: Interval = Query(default=Interval.DAY_1),
) -> dict:
    query = GetSymbolSyncStatusQuery(symbol=symbol, exchange=exchange, interval=interval.value)
    status = await mediator.send(query)

    return {
        "symbol": status.symbol,
        "exchange": status.exchange,
        "interval": status.interval,
        "status": status.status,
        "bar_count": status.bar_count,
        "last_sync_at": status.last_sync_at,
        "last_bar_at": status.last_bar_at,
        "error_message": status.error_message,
    }
