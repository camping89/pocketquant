"""API route for getting the current aggregating bar."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query

from src.application.market_data.quote_service import QuoteService
from src.common.exceptions import NotFoundError
from src.domain.shared.value_objects import Interval

router = APIRouter(route_class=DishkaRoute)


@router.get("/current-bar/{exchange}/{symbol}")
async def get_current_bar(
    exchange: str,
    symbol: str,
    quote_service: FromDishka[QuoteService],
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> dict:
    bar = await quote_service.bar_manager.get_current_bar(symbol, exchange, interval)

    if bar is None:
        raise NotFoundError(f"No current bar for {exchange}:{symbol} at {interval.value}")

    return bar
