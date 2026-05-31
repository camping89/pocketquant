"""Route for backfilling historical bars for a tracked symbol — admin only.

POST /api/v1/market-data/tracked-symbols/{symbol}/backfill
  ``symbol`` path param is URL-encoded composite ``{code}:{exchange}`` (e.g. BTCUSDT%3ABINANCE).
Query params:
  interval  — timeframe (1m, 5m, 15m, 1h, 4h, 1d)
  n         — number of bars (default 100, max 5000)
  mode      — cascade | direct | auto (default auto)

Returns: {persisted_count: int, mode_used: str}
"""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query
from pocketquant.api.common.symbol_validation import validate_composite_symbol
from pocketquant.api.market_data.handlers.tracked_symbols.backfill.command import (
    BackfillTrackedSymbolCommand,
)
from pocketquant.api.market_data.handlers.tracked_symbols.backfill.handler import (
    BackfillTrackedSymbolHandler,
)
from pocketquant.api.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.market_data.interfaces import IDataProvider
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository

router = APIRouter(route_class=DishkaRoute)


@router.post(
    "/tracked-symbols/{symbol}/backfill",
    response_model=dict,
)
async def backfill_tracked_symbol(
    symbol: str,
    provider: FromDishka[IDataProvider],
    bar_repository: FromDishka[BarRepository],
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
    handler = BackfillTrackedSymbolHandler(
        provider=provider,
        bar_repository=bar_repository,
    )
    return await handler.handle(cmd)
