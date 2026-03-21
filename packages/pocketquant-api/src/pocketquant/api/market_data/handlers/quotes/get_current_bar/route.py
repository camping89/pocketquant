"""API route for getting the current aggregating bar."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.domain.shared.value_objects import Interval

router = APIRouter(route_class=DishkaRoute)


@router.get("/current-bar/{exchange}/{symbol}")
async def get_current_bar(
    exchange: str,
    symbol: str,
    quote_app_service: FromDishka[QuoteAppService],
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> dict:
    bar = await quote_app_service.bar_manager.get_current_bar(symbol, exchange, interval)

    if bar is None:
        raise NotFoundError(f"No current bar for {exchange}:{symbol} at {interval.value}")

    return bar
