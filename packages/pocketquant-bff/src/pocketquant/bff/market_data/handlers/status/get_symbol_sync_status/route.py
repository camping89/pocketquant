"""Route for getting sync status for a specific composite symbol.

Path: GET /sync-status/{symbol}
``{symbol}`` is URL-encoded composite, e.g. ``BTCUSDT%3ABINANCE``.
"""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from pocketquant.bff.common.symbol_validation import validate_composite_symbol
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.execution.market_data.handlers.status.get_symbol_sync_status.query import (
    GetSymbolSyncStatusQuery,
)

router = APIRouter(route_class=DishkaRoute)


@router.get("/sync-status/{symbol}")
async def get_symbol_sync_status(
    symbol: str,
    mediator: FromDishka[Mediator],
    interval: Interval = Query(default=Interval.DAY_1),
) -> dict:
    symbol = validate_composite_symbol(symbol)
    query = GetSymbolSyncStatusQuery(symbol=symbol, interval=interval.value)
    status = await mediator.send(query)

    return {
        "symbol": status.symbol,
        "interval": status.interval,
        "status": status.status,
        "bar_count": status.bar_count,
        "last_sync_at": status.last_sync_at,
        "last_bar_at": status.last_bar_at,
        "error_message": status.error_message,
    }
