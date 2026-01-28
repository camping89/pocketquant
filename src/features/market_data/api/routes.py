from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.common.constants import (
    COLLECTION_SYMBOLS,
    LIMIT_OHLCV_QUERY_MAX,
    LIMIT_TVDATAFEED_MAX_BARS,
)
from src.common.database import Database
from src.common.logging import get_logger
from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.models.ohlcv import Interval, OHLCVResponse
from src.features.market_data.ohlcv import GetOHLCVQuery
from src.features.market_data.status import (
    GetSymbolSyncStatusQuery,
    GetSyncStatusQuery,
)
from src.features.market_data.sync import BulkSyncCommand, SyncSymbolCommand

logger = get_logger(__name__)

router = APIRouter(prefix="/market-data", tags=["Market Data"])


class SyncRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL, BTCUSD)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ, BINANCE)")
    interval: Interval = Field(default=Interval.DAY_1, description="Time interval")
    n_bars: int = Field(
        default=LIMIT_TVDATAFEED_MAX_BARS,
        ge=1,
        le=LIMIT_TVDATAFEED_MAX_BARS,
        description="Number of bars to fetch",
    )


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
    n_bars: int = Field(default=LIMIT_TVDATAFEED_MAX_BARS, ge=1, le=LIMIT_TVDATAFEED_MAX_BARS)


@router.post("/sync", response_model=SyncResponse)
async def sync_symbol(
    request: SyncRequest,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> SyncResponse:
    logger.info(
        "api.sync_requested",
        symbol=request.symbol,
        exchange=request.exchange,
        interval=request.interval.value,
    )

    cmd = SyncSymbolCommand(
        symbol=request.symbol,
        exchange=request.exchange,
        interval=request.interval.value,
        n_bars=request.n_bars,
    )

    result = await mediator.send(cmd)

    return SyncResponse(
        symbol=result.symbol,
        exchange=result.exchange,
        interval=result.interval,
        status=result.status,
        bars_synced=result.bars_synced,
        total_bars=result.total_bars,
        message=result.message,
    )


@router.post("/sync/background", response_model=dict)
async def sync_symbol_background(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    async def run_sync() -> None:
        cmd = SyncSymbolCommand(
            symbol=request.symbol,
            exchange=request.exchange,
            interval=request.interval.value,
            n_bars=request.n_bars,
        )
        await mediator.send(cmd)

    background_tasks.add_task(run_sync)

    return {
        "status": "accepted",
        "message": f"Sync started for {request.symbol}:{request.exchange}",
    }


@router.post("/sync/bulk", response_model=list[SyncResponse])
async def sync_bulk(
    request: BulkSyncRequest,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> list[SyncResponse]:
    cmd = BulkSyncCommand(
        symbols=request.symbols,
        interval=request.interval.value,
        n_bars=request.n_bars,
    )

    results = await mediator.send(cmd)

    return [
        SyncResponse(
            symbol=r.symbol,
            exchange=r.exchange,
            interval=r.interval,
            status=r.status,
            bars_synced=r.bars_synced,
            total_bars=r.total_bars,
            message=r.message,
        )
        for r in results
    ]


@router.get("/ohlcv/{exchange}/{symbol}", response_model=OHLCVResponse)
async def get_ohlcv(
    exchange: str,
    symbol: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
    interval: Interval = Query(default=Interval.DAY_1),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=LIMIT_OHLCV_QUERY_MAX),
) -> OHLCVResponse:
    query = GetOHLCVQuery(
        symbol=symbol,
        exchange=exchange,
        interval=interval.value,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    bars = await mediator.send(query)

    return OHLCVResponse(
        symbol=symbol.upper(),
        exchange=exchange.upper(),
        interval=interval.value,
        data=bars,
        count=len(bars),
    )


@router.get("/symbols")
async def list_symbols(
    exchange: str | None = Query(default=None, description="Filter by exchange"),
) -> list[dict]:
    collection = Database.get_collection(COLLECTION_SYMBOLS)

    query = {}
    if exchange:
        query["exchange"] = exchange.upper()

    cursor = collection.find(query).sort("symbol", 1)

    return [
        {
            "symbol": doc["symbol"],
            "exchange": doc["exchange"],
            "name": doc.get("name"),
            "asset_type": doc.get("asset_type"),
            "is_active": doc.get("is_active", True),
        }
        async for doc in cursor
    ]


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
