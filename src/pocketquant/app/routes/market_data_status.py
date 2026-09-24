from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query

from pocketquant.app.common.symbol_validation import validate_composite_symbol
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.data_lag_service import (
    DataLagQueryService,
    DataLagResponse,
    GetDataLagQuery,
)
from pocketquant.engine.market_data.sync_status_service import (
    GetSymbolSyncStatusQuery,
    GetSyncStatusQuery,
    SyncStatusQueryService,
)

router = APIRouter(route_class=DishkaRoute)


@router.get("/sync-status")
async def get_sync_statuses(
    sync_status_service: FromDishka[SyncStatusQueryService],
) -> list[dict]:
    query = GetSyncStatusQuery()
    statuses = await sync_status_service.get_sync_status(query)

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
            "is_market_open": s.is_market_open,
            "lag_seconds": s.lag_seconds,
            "is_delayed": s.is_delayed,
        }
        for s in statuses
    ]


@router.get("/sync-status/{symbol}")
async def get_symbol_sync_status(
    symbol: str,
    sync_status_service: FromDishka[SyncStatusQueryService],
    interval: Interval = Query(default=Interval.DAY_1),
) -> dict:
    symbol = validate_composite_symbol(symbol)
    query = GetSymbolSyncStatusQuery(symbol=symbol, interval=interval.value)
    status = await sync_status_service.get_symbol_sync_status(query)

    return {
        "symbol": status.symbol,
        "interval": status.interval,
        "status": status.status,
        "bar_count": status.bar_count,
        "last_sync_at": status.last_sync_at,
        "last_bar_at": status.last_bar_at,
        "error_message": status.error_message,
        "is_market_open": status.is_market_open,
        "is_stuck": status.is_stuck,
        "lag_seconds": status.lag_seconds,
        "is_delayed": status.is_delayed,
    }


@router.get("/data-lag/{symbol}", response_model=DataLagResponse)
async def get_data_lag(
    symbol: str,
    data_lag_service: FromDishka[DataLagQueryService],
) -> DataLagResponse:
    """How far this symbol's data runs behind real time, as the minute check last saw it."""
    symbol = validate_composite_symbol(symbol)
    return await data_lag_service.get_data_lag(GetDataLagQuery(symbol=symbol))
