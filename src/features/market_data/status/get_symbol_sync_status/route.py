"""Route for getting sync status for a specific symbol."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.base.models.ohlcv import Interval
from src.features.market_data.status.get_symbol_sync_status.query import (
    GetSymbolSyncStatusQuery,
)

router = APIRouter()


@router.get("/sync-status/{exchange}/{symbol}")
async def get_symbol_sync_status(
    exchange: str,
    symbol: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
    interval: Interval = Query(default=Interval.DAY_1),
) -> dict:
    query = GetSymbolSyncStatusQuery(
        symbol=symbol, exchange=exchange, interval=interval.value
    )

    try:
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
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
