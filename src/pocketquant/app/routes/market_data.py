"""Market-data routes under ``/market-data``: sync, integrity, OHLCV and SSE bars,
sync status, symbols, and tracked symbols.

``symbol`` path params are URL-encoded composite ``{code}:{exchange}``
(e.g. ``BTCUSDT%3ABINANCE``). Tracked-symbol writes require X-Admin-Token.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from pocketquant.app.common.symbol_validation import validate_composite_symbol
from pocketquant.app.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.common.constants import LIMIT_OHLCV_QUERY_MAX
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import SOURCE_REST_REPAIR
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService
from pocketquant.engine.market_data.bar_integrity import check_integrity, repair_integrity
from pocketquant.engine.market_data.ohlcv_service import GetOHLCVQuery, OhlcvService
from pocketquant.engine.market_data.symbols_service import SymbolQueryService
from pocketquant.engine.market_data.sync_policy import SyncPolicies
from pocketquant.engine.market_data.sync_service import (
    BulkSyncCommand,
    SyncResponse,
    SyncService,
    SyncSymbolCommand,
)
from pocketquant.engine.market_data.sync_status_service import SyncStatusQueryService
from pocketquant.engine.market_data.tracked_symbols_backfill import (
    BackfillTrackedSymbolCommand,
    TrackedSymbolBackfillService,
)
from pocketquant.engine.market_data.tracked_symbols_service import (
    AddTrackedSymbolCommand,
    TrackedSymbolService,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)
tracked_symbols_router = APIRouter(tags=["Tracked Symbols"], route_class=DishkaRoute)

# Poll interval — 1s (200ms throttle + 1s poll ≤ 1.2s max lag)
_POLL_INTERVAL = 1.0


class IntegrityRequest(BaseModel):
    """Request body for integrity check/repair. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    interval: Interval
    days_back: int = Field(default=7, ge=1, le=90)


class OHLCVResponse(BaseModel):
    """``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    interval: str
    data: list[dict[str, Any]]
    count: int


@router.post("/sync", response_model=SyncResponse)
async def sync_symbol(
    cmd: SyncSymbolCommand,
    sync_service: FromDishka[SyncService],
) -> SyncResponse:
    """Sync historical OHLCV data. ``symbol`` in body is composite ``{code}:{exchange}``."""
    logger.info(
        "api.sync_requested",
        symbol=cmd.symbol,
        interval=cmd.interval.value,
    )
    return await sync_service.sync_one(cmd)


@router.post("/sync/background", response_model=dict)
async def sync_symbol_background(
    cmd: SyncSymbolCommand,
    background_tasks: BackgroundTasks,
    sync_service: FromDishka[SyncService],
) -> dict:
    background_tasks.add_task(sync_service.sync_one, cmd)

    return {
        "status": "accepted",
        "message": f"Sync started for {cmd.symbol}",
    }


@router.post("/sync/bulk", response_model=list[SyncResponse])
async def sync_bulk(
    cmd: BulkSyncCommand,
    sync_service: FromDishka[SyncService],
) -> list[SyncResponse]:
    return await sync_service.sync_bulk(cmd)


@router.post("/integrity/check")
async def integrity_check(
    body: IntegrityRequest,
    bar_repo: FromDishka[BarRepository],
    policies: FromDishka[SyncPolicies],
) -> dict:
    symbol = validate_composite_symbol(body.symbol)
    return await check_integrity(
        symbol,
        body.interval,
        bar_repo,
        body.days_back,
        calendar=policies.market_calendar(symbol),
    )


@router.post("/integrity/repair")
async def integrity_repair(
    body: IntegrityRequest,
    bar_repo: FromDishka[BarRepository],
    sync_service: FromDishka[SyncService],
    policies: FromDishka[SyncPolicies],
) -> dict:
    symbol = validate_composite_symbol(body.symbol)
    # source is keyword-only; days_back must be passed by name too (it follows the
    # `*` marker). Repaired bars are tagged with the REST-repair provenance.
    return await repair_integrity(
        symbol,
        body.interval,
        bar_repo,
        sync_service,
        source=SOURCE_REST_REPAIR,
        days_back=body.days_back,
        calendar=policies.market_calendar(symbol),
    )


@router.get("/ohlcv/{symbol}/{interval}", response_model=OHLCVResponse)
async def get_ohlcv(
    symbol: str,
    interval: Interval,
    ohlcv_service: FromDishka[OhlcvService],
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=LIMIT_OHLCV_QUERY_MAX),
) -> OHLCVResponse:
    symbol = validate_composite_symbol(symbol)
    query = GetOHLCVQuery(
        symbol=symbol,
        interval=interval.value,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    result = await ohlcv_service.get_ohlcv(query)

    return OHLCVResponse(
        symbol=result.symbol,
        interval=result.interval,
        data=result.data,
        count=result.count,
    )


def _make_payload(bar: dict[str, Any], interval: Interval) -> dict[str, Any]:
    """Build unified SSE payload from bar dict (Redis or Mongo fallback shape).

    Redis shape: includes 'last_update' timestamp + 'bar_start' as ISO string.
    Mongo fallback shape: same keys, no 'last_update', tick_count=0.
    is_in_progress=True when sourced from Redis (live in-progress bar).
    staleness_ms=None when Mongo source; ms since last update when Redis source.
    """
    last_update = bar.get("last_update")
    is_in_progress = last_update is not None

    staleness_ms: int | None = None
    if is_in_progress and isinstance(last_update, (int, float)):
        staleness_ms = max(0, int((time.time() - last_update) * 1000))

    return {
        "symbol": bar.get("symbol"),
        "interval": interval.value,
        "bar_start": bar.get("bar_start"),
        "open": bar.get("open"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "close": bar.get("close"),
        "volume": bar.get("volume"),
        "tick_count": bar.get("tick_count", 0),
        "is_in_progress": is_in_progress,
        "staleness_ms": staleness_ms,
    }


@router.get("/bars/stream/{symbol}")
async def stream_bars(
    symbol: str,
    request: Request,
    bar_service: FromDishka[BarAppService],
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> StreamingResponse:
    """SSE stream — polls Redis (in-progress) + Mongo fallback, emits on change.

    ``{symbol}`` path param is URL-encoded composite (e.g. ``BTCUSDT%3ABINANCE``).
    Validates composite format (400 on mismatch).
    Validates ?interval against Interval enum; returns 400 with INVALID_INTERVAL
    if unknown value.
    """
    symbol = validate_composite_symbol(symbol)

    async def event_generator():
        last_bar_start: str | None = None
        last_close: float | None = None
        last_volume: float | None = None

        # Emit initial bar immediately on connect
        try:
            bar = await bar_service.get_current_bar(symbol, interval)
            if bar is not None:
                last_bar_start = bar.get("bar_start")
                last_close = bar.get("close")
                last_volume = bar.get("volume")
                payload = _make_payload(bar, interval)
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            logger.error("sse.bars.init_error", error=str(e))

        # Poll loop — emit when bar_start, close, or volume changes
        try:
            while True:
                await asyncio.sleep(_POLL_INTERVAL)

                bar = await bar_service.get_current_bar(symbol, interval)
                if bar is None:
                    continue

                bar_start = bar.get("bar_start")
                close = bar.get("close")
                volume = bar.get("volume")

                bar_changed = bar_start != last_bar_start
                ohlcv_changed = close != last_close or volume != last_volume

                if not bar_changed and not ohlcv_changed:
                    continue

                last_bar_start = bar_start
                last_close = close
                last_volume = volume
                yield f"data: {json.dumps(_make_payload(bar, interval))}\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("sse.bars.poll_error", error=str(e))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        },
    )


@router.get("/sync-status")
async def get_sync_statuses(
    sync_status_service: FromDishka[SyncStatusQueryService],
) -> list[dict]:
    statuses = await sync_status_service.get_sync_status()

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


@router.get("/sync-status/{symbol}")
async def get_symbol_sync_status(
    symbol: str,
    sync_status_service: FromDishka[SyncStatusQueryService],
    interval: Interval = Query(default=Interval.DAY_1),
) -> dict:
    symbol = validate_composite_symbol(symbol)
    status = await sync_status_service.get_symbol_sync_status(symbol, interval.value)

    return {
        "symbol": status.symbol,
        "interval": status.interval,
        "status": status.status,
        "bar_count": status.bar_count,
        "last_sync_at": status.last_sync_at,
        "last_bar_at": status.last_bar_at,
        "error_message": status.error_message,
    }


@router.get("/symbols")
async def list_symbols(
    symbol_service: FromDishka[SymbolQueryService],
) -> list[dict]:
    return await symbol_service.list_symbols()


@tracked_symbols_router.get("/tracked-symbols", response_model=list[dict])
async def list_tracked_symbols(service: FromDishka[TrackedSymbolService]) -> list[dict]:
    return await service.list_all()


@tracked_symbols_router.post(
    "/tracked-symbols", response_model=dict, dependencies=[Depends(verify_admin_token)]
)
async def add_tracked_symbol(
    cmd: AddTrackedSymbolCommand,
    service: FromDishka[TrackedSymbolService],
) -> dict:
    """Add (exchange, symbol) to tracked list. Idempotent. Requires X-Admin-Token."""
    return await service.add(cmd)


@tracked_symbols_router.put(
    "/tracked-symbols/{symbol}",
    response_model=dict,
    dependencies=[Depends(verify_admin_token)],
)
async def update_tracked_symbol(
    symbol: str,
    service: FromDishka[TrackedSymbolService],
) -> dict:
    """Update metadata for a tracked symbol. Requires X-Admin-Token.

    ``symbol`` path param is URL-encoded composite ``{code}:{exchange}``
    (e.g. ``BTCUSDT%3ABINANCE``).
    """
    symbol = validate_composite_symbol(symbol)
    return await service.update(symbol)


@tracked_symbols_router.delete(
    "/tracked-symbols/{symbol}",
    response_model=dict,
    dependencies=[Depends(verify_admin_token)],
)
async def remove_tracked_symbol(
    symbol: str,
    service: FromDishka[TrackedSymbolService],
) -> dict:
    """Remove a symbol and all data that references it. Requires X-Admin-Token.

    Cascades to symbols, bars, sync_status, subscriptions (stopped first),
    backtest runs/orders/trades, live orders/positions, job_history details and
    symbol-keyed cache keys. Idempotent: always 200, ``deleted`` holds
    per-collection counts. ``symbol`` path param is URL-encoded composite
    ``{code}:{exchange}`` (e.g. ``BTCUSDT%3ABINANCE``).
    """
    symbol = validate_composite_symbol(symbol)
    return await service.remove(symbol)


@tracked_symbols_router.post(
    "/tracked-symbols/{symbol}/backfill",
    response_model=dict,
)
async def backfill_tracked_symbol(
    symbol: str,
    service: FromDishka[TrackedSymbolBackfillService],
    interval: Interval = Query(default=Interval.MINUTE_1, description="Timeframe to backfill"),
    n: int = Query(default=100, ge=1, le=5000, description="Number of bars"),
    mode: str = Query(default="auto", description="cascade | direct | auto"),
    _admin: None = Depends(verify_admin_token),
) -> dict:
    """Backfill historical bars for one tracked symbol. Requires X-Admin-Token.

    ``symbol`` is composite ``{code}:{exchange}`` — URL-encode ``:`` as ``%3A``.
    mode=cascade: REST-fetch 1m bars, upsert, cascade to requested tf (default for >=5m).
    mode=direct:  REST-fetch the requested tf directly (default for 1m).
    mode=auto:    select mode based on interval (cascade for >=5m, direct for 1m).
    """
    symbol = validate_composite_symbol(symbol)
    cmd = BackfillTrackedSymbolCommand(
        symbol=symbol,
        interval=interval,
        n=n,
        mode=mode,
    )
    return await service.run(cmd)
