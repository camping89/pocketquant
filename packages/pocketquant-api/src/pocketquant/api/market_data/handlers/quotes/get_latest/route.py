"""API route for getting the latest quote.

Path: GET /latest/{symbol}
``{symbol}`` is URL-encoded composite, e.g. ``BTCUSDT%3ABINANCE``.
"""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.api.common.symbol_validation import validate_composite_symbol
from pocketquant.api.market_data.handlers.quotes.get_latest.query import GetLatestQuoteQuery
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Mediator
from pydantic import BaseModel

router = APIRouter(route_class=DishkaRoute)


class QuoteResponse(BaseModel):
    """``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    timestamp: str
    last_price: float
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None

    @classmethod
    def from_result(cls, result) -> "QuoteResponse":
        return cls(
            symbol=result.symbol,
            timestamp=result.timestamp,
            last_price=result.last_price,
            bid=result.bid,
            ask=result.ask,
            volume=result.volume,
            change=result.change,
            change_percent=result.change_percent,
            open_price=result.open_price,
            high_price=result.high_price,
            low_price=result.low_price,
        )


@router.get("/latest/{symbol}", response_model=QuoteResponse)
async def get_latest_quote(
    symbol: str,
    mediator: FromDishka[Mediator],
) -> QuoteResponse:
    symbol = validate_composite_symbol(symbol)
    query = GetLatestQuoteQuery(symbol=symbol)
    result = await mediator.send(query)

    if result is None:
        raise NotFoundError(f"No quote found for {symbol}. Make sure you're subscribed.")

    return QuoteResponse.from_result(result)
