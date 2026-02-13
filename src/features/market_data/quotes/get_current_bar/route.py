"""API route for getting the current aggregating bar."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.config import Settings, get_settings
from src.features.market_data.base.models.ohlcv import Interval
from src.features.market_data.quotes.quote_service import get_quote_service

router = APIRouter()


@router.get("/current-bar/{exchange}/{symbol}")
async def get_current_bar(
    exchange: str,
    symbol: str,
    settings: Annotated[Settings, Depends(get_settings)],
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> dict:
    state = get_quote_service(settings)
    bar = await state.bar_manager.get_current_bar(symbol, exchange, interval)

    if bar is None:
        raise HTTPException(
            status_code=404,
            detail=f"No current bar for {exchange}:{symbol} at {interval.value}",
        )

    return bar
