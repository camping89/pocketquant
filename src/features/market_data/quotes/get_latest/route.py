"""API route for getting the latest quote."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.common.exceptions import NotFoundError
from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.quotes.get_latest.query import GetLatestQuoteQuery

router = APIRouter()


class QuoteResponse(BaseModel):
    symbol: str
    exchange: str
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
    def from_result(cls, result) -> QuoteResponse:
        return cls(
            symbol=result.symbol,
            exchange=result.exchange,
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


@router.get("/latest/{exchange}/{symbol}", response_model=QuoteResponse)
async def get_latest_quote(
    exchange: str,
    symbol: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> QuoteResponse:
    query = GetLatestQuoteQuery(symbol=symbol, exchange=exchange)
    result = await mediator.send(query)

    if result is None:
        raise NotFoundError(
            f"No quote found for {exchange}:{symbol}. Make sure you're subscribed."
        )

    return QuoteResponse.from_result(result)
