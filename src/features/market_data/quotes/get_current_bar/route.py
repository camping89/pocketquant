"""API route for getting the current aggregating bar."""

from fastapi import APIRouter, Query, Request

from src.common.exceptions import NotFoundError
from src.domain.shared.value_objects import Interval

router = APIRouter()


@router.get("/current-bar/{exchange}/{symbol}")
async def get_current_bar(
    exchange: str,
    symbol: str,
    request: Request,
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> dict:
    quote_service = request.app.state.container.quote_service()
    bar = await quote_service.bar_manager.get_current_bar(symbol, exchange, interval)

    if bar is None:
        raise NotFoundError(f"No current bar for {exchange}:{symbol} at {interval.value}")

    return bar
