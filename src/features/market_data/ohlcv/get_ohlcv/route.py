"""Route for getting OHLCV data."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.common.constants import LIMIT_OHLCV_QUERY_MAX
from src.common.mediator import Mediator
from src.dependencies import get_mediator
from src.domain.shared.value_objects import Interval
from src.features.market_data.ohlcv.get_ohlcv.query import GetOHLCVQuery
from src.persistence.schemas.ohlcv_schema import OHLCVResponse

router = APIRouter()


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
