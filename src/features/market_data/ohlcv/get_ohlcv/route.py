"""Route for getting OHLCV data."""

from datetime import datetime
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.common.constants import LIMIT_OHLCV_QUERY_MAX
from src.common.mediator import Mediator
from src.domain.shared.value_objects import Interval
from src.features.market_data.ohlcv.get_ohlcv.query import GetOHLCVQuery


class OHLCVResponse(BaseModel):
    symbol: str
    exchange: str
    interval: str
    data: list[dict[str, Any]]
    count: int

router = APIRouter(route_class=DishkaRoute)


@router.get("/ohlcv/{exchange}/{symbol}", response_model=OHLCVResponse)
async def get_ohlcv(
    exchange: str,
    symbol: str,
    mediator: FromDishka[Mediator],
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
