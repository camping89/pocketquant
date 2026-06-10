"""tracked_symbols routes — CRUD + backfill under /tracked-symbols.

``symbol`` path params are URL-encoded composite ``{code}:{exchange}``
(e.g. ``BTCUSDT%3ABINANCE``). Writes require X-Admin-Token; list is public.
"""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query

from pocketquant.bff.common.symbol_validation import validate_composite_symbol
from pocketquant.bff.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.tracked_symbols_backfill import (
    BackfillTrackedSymbolCommand,
    TrackedSymbolBackfillService,
)
from pocketquant.engine.market_data.tracked_symbols_service import (
    AddTrackedSymbolCommand,
    ListTrackedSymbolsQuery,
    RemoveTrackedSymbolCommand,
    TrackedSymbolService,
    UpdateTrackedSymbolCommand,
)

router = APIRouter(tags=["Tracked Symbols"], route_class=DishkaRoute)


@router.get("/tracked-symbols", response_model=list[dict])
async def list_tracked_symbols(service: FromDishka[TrackedSymbolService]) -> list[dict]:
    """List all symbols tracked for live data pipelines. No auth required."""
    return await service.list_all(ListTrackedSymbolsQuery())


@router.post("/tracked-symbols", response_model=dict, dependencies=[Depends(verify_admin_token)])
async def add_tracked_symbol(
    cmd: AddTrackedSymbolCommand,
    service: FromDishka[TrackedSymbolService],
) -> dict:
    """Add (exchange, symbol) to tracked list. Idempotent. Requires X-Admin-Token."""
    return await service.add(cmd)


@router.put(
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
    cmd = UpdateTrackedSymbolCommand(symbol=symbol)
    return await service.update(cmd)


@router.delete(
    "/tracked-symbols/{symbol}",
    response_model=dict,
    dependencies=[Depends(verify_admin_token)],
)
async def remove_tracked_symbol(
    symbol: str,
    service: FromDishka[TrackedSymbolService],
) -> dict:
    """Remove composite symbol from tracked list. Requires X-Admin-Token.

    ``symbol`` path param is URL-encoded composite ``{code}:{exchange}``
    (e.g. ``BTCUSDT%3ABINANCE``).
    """
    symbol = validate_composite_symbol(symbol)
    cmd = RemoveTrackedSymbolCommand(symbol=symbol)
    return await service.remove(cmd)


@router.post(
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
