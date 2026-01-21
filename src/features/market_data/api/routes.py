from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.common.logging import get_logger
from src.config import Settings, get_settings
from src.features.market_data.models.ohlcv import Interval, OHLCVResponse
from src.features.market_data.repositories.ohlcv_repository import OHLCVRepository
from src.features.market_data.repositories.symbol_repository import SymbolRepository
from src.features.market_data.services.data_sync_service import DataSyncService

logger = get_logger(__name__)

router = APIRouter(prefix="/market-data", tags=["Market Data"])


class SyncRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL, BTCUSD)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ, BINANCE)")
    interval: Interval = Field(default=Interval.DAY_1, description="Time interval")
    n_bars: int = Field(default=5000, ge=1, le=5000, description="Number of bars to fetch")


class SyncResponse(BaseModel):
    symbol: str
    exchange: str
    interval: str
    status: str
    message: str | None = None
    bars_synced: int = 0
    total_bars: int | None = None


class BulkSyncRequest(BaseModel):
    symbols: list[dict] = Field(
        ...,
        description="List of symbols with 'symbol' and 'exchange' keys",
        example=[
            {"symbol": "AAPL", "exchange": "NASDAQ"},
            {"symbol": "BTCUSD", "exchange": "BINANCE"},
        ],
    )
    interval: Interval = Field(default=Interval.DAY_1)
    n_bars: int = Field(default=5000, ge=1, le=5000)


def get_data_sync_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DataSyncService:
    return DataSyncService(settings)


@router.post("/sync", response_model=SyncResponse)
async def sync_symbol(
    request: SyncRequest,
    service: Annotated[DataSyncService, Depends(get_data_sync_service)],
) -> SyncResponse:
    logger.info(
        "api_sync_symbol",
        symbol=request.symbol,
        exchange=request.exchange,
        interval=request.interval.value,
    )

    try:
        result = await service.sync_symbol(
            symbol=request.symbol,
            exchange=request.exchange,
            interval=request.interval,
            n_bars=request.n_bars,
        )

        return SyncResponse(**result)

    finally:
        service.close()


@router.post("/sync/background", response_model=dict)
async def sync_symbol_background(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    async def run_sync() -> None:
        service = DataSyncService(settings)
        try:
            await service.sync_symbol(
                symbol=request.symbol,
                exchange=request.exchange,
                interval=request.interval,
                n_bars=request.n_bars,
            )
        finally:
            service.close()

    background_tasks.add_task(run_sync)

    return {
        "status": "accepted",
        "message": f"Sync started for {request.symbol}:{request.exchange}",
    }


@router.post("/sync/bulk", response_model=list[SyncResponse])
async def sync_bulk(
    request: BulkSyncRequest,
    service: Annotated[DataSyncService, Depends(get_data_sync_service)],
) -> list[SyncResponse]:
    try:
        results = await service.sync_multiple_symbols(
            symbols=request.symbols,
            interval=request.interval,
            n_bars=request.n_bars,
        )

        return [SyncResponse(**r) for r in results]

    finally:
        service.close()


@router.get("/ohlcv/{exchange}/{symbol}", response_model=OHLCVResponse)
async def get_ohlcv(
    exchange: str,
    symbol: str,
    interval: Interval = Query(default=Interval.DAY_1),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    service: DataSyncService = Depends(get_data_sync_service),
) -> OHLCVResponse:
    try:
        bars = await service.get_cached_bars(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

        return OHLCVResponse(
            symbol=symbol.upper(),
            exchange=exchange.upper(),
            interval=interval.value,
            data=bars,
            count=len(bars),
        )

    finally:
        service.close()


@router.get("/symbols")
async def list_symbols(
    exchange: str | None = Query(default=None, description="Filter by exchange"),
) -> list[dict]:
    symbols = await SymbolRepository.get_all(exchange=exchange)

    return [
        {
            "symbol": s.symbol,
            "exchange": s.exchange,
            "name": s.name,
            "asset_type": s.asset_type,
            "is_active": s.is_active,
        }
        for s in symbols
    ]


@router.get("/sync-status")
async def get_sync_statuses() -> list[dict]:
    statuses = await OHLCVRepository.get_all_sync_statuses()

    return [
        {
            "symbol": s.symbol,
            "exchange": s.exchange,
            "interval": s.interval,
            "status": s.status,
            "bar_count": s.bar_count,
            "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
            "last_bar_at": s.last_bar_at.isoformat() if s.last_bar_at else None,
            "error_message": s.error_message,
        }
        for s in statuses
    ]


@router.get("/sync-status/{exchange}/{symbol}")
async def get_symbol_sync_status(
    exchange: str,
    symbol: str,
    interval: Interval = Query(default=Interval.DAY_1),
) -> dict:
    status = await OHLCVRepository.get_sync_status(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
    )

    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"No sync status found for {symbol}:{exchange}",
        )

    return {
        "symbol": status.symbol,
        "exchange": status.exchange,
        "interval": status.interval,
        "status": status.status,
        "bar_count": status.bar_count,
        "last_sync_at": status.last_sync_at.isoformat() if status.last_sync_at else None,
        "last_bar_at": status.last_bar_at.isoformat() if status.last_bar_at else None,
        "error_message": status.error_message,
    }
