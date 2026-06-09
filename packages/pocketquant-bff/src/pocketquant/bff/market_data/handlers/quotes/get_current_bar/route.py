"""API route for getting the current aggregating bar.

Path: GET /current-bar/{symbol}
``{symbol}`` is URL-encoded composite, e.g. ``BTCUSDT%3ABINANCE``.
"""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from pocketquant.bff.common.symbol_validation import validate_composite_symbol
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.execution.market_data.app_services.bar_app_service import BarAppService

router = APIRouter(route_class=DishkaRoute)


@router.get("/current-bar/{symbol}")
async def get_current_bar(
    symbol: str,
    bar_service: FromDishka[BarAppService],
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> dict:
    # bff reads the current bar straight from Cache (live feed writes it) with a
    # DB fallback — no WS runtime needed, so the bff BarAppService carries only
    # Cache + BarRepository.
    symbol = validate_composite_symbol(symbol)
    bar = await bar_service.get_current_bar(symbol, interval)

    if bar is None:
        raise NotFoundError(f"No current bar for {symbol} at {interval.value}")

    return bar
