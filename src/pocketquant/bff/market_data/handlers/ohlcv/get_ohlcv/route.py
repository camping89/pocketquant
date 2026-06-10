"""Route for getting OHLCV data.

Path: GET /ohlcv/{symbol}/{interval}
``{symbol}`` is URL-encoded composite, e.g. ``BTCUSDT%3ABINANCE``.
FastAPI auto-decodes ``%3A`` → ``:`` before the handler sees the value.
"""

from datetime import datetime
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from pydantic import BaseModel

from pocketquant.bff.common.symbol_validation import validate_composite_symbol
from pocketquant.core.common.constants import LIMIT_OHLCV_QUERY_MAX
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.handlers.ohlcv.get_ohlcv.query import GetOHLCVQuery


class OHLCVResponse(BaseModel):
    """``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    interval: str
    data: list[dict[str, Any]]
    count: int


router = APIRouter(route_class=DishkaRoute)


@router.get("/ohlcv/{symbol}/{interval}", response_model=OHLCVResponse)
async def get_ohlcv(
    symbol: str,
    interval: Interval,
    mediator: FromDishka[Mediator],
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

    bars = await mediator.send(query)

    return OHLCVResponse(
        symbol=symbol,
        interval=interval.value,
        data=bars,
        count=len(bars),
    )
