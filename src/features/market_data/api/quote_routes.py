from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.common.logging import get_logger
from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.config import Settings, get_settings
from src.features.market_data.models.ohlcv import Interval
from src.features.market_data.quote import (
    GetAllQuotesQuery,
    GetLatestQuoteQuery,
    StartQuoteFeedCommand,
    StopQuoteFeedCommand,
    SubscribeCommand,
    UnsubscribeCommand,
)
from src.features.market_data.quote.handler import get_quote_state
from src.features.market_data.status import GetQuoteServiceStatusQuery

logger = get_logger(__name__)

router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"])


class SubscribeRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ)")


class SubscribeResponse(BaseModel):
    subscription_key: str
    message: str


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


class QuoteServiceStatus(BaseModel):
    running: bool
    subscription_count: int
    active_symbols: list[str]


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_to_symbol(
    request: SubscribeRequest,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> SubscribeResponse:
    cmd = SubscribeCommand(symbol=request.symbol, exchange=request.exchange)

    try:
        result = await mediator.send(cmd)
        return SubscribeResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/unsubscribe")
async def unsubscribe_from_symbol(
    request: SubscribeRequest,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    cmd = UnsubscribeCommand(symbol=request.symbol, exchange=request.exchange)
    return await mediator.send(cmd)


@router.get("/latest/{exchange}/{symbol}", response_model=QuoteResponse)
async def get_latest_quote(
    exchange: str,
    symbol: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> QuoteResponse:
    query = GetLatestQuoteQuery(symbol=symbol, exchange=exchange)
    result = await mediator.send(query)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No quote found for {exchange}:{symbol}. Make sure you're subscribed.",
        )

    return QuoteResponse.from_result(result)


@router.get("/all", response_model=list[QuoteResponse])
async def get_all_quotes(
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> list[QuoteResponse]:
    query = GetAllQuotesQuery()
    results = await mediator.send(query)
    return [QuoteResponse.from_result(r) for r in results]


@router.get("/current-bar/{exchange}/{symbol}")
async def get_current_bar(
    exchange: str,
    symbol: str,
    settings: Annotated[Settings, Depends(get_settings)],
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> dict:
    state = get_quote_state(settings)
    bar = await state.bar_manager.get_current_bar(symbol, exchange, interval)

    if bar is None:
        raise HTTPException(
            status_code=404,
            detail=f"No current bar for {exchange}:{symbol} at {interval.value}",
        )

    return bar


@router.post("/start")
async def start_quote_service(
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    cmd = StartQuoteFeedCommand()
    return await mediator.send(cmd)


@router.post("/stop")
async def stop_quote_service(
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    cmd = StopQuoteFeedCommand()
    return await mediator.send(cmd)


@router.get("/status", response_model=QuoteServiceStatus)
async def get_quote_service_status(
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> QuoteServiceStatus:
    query = GetQuoteServiceStatusQuery()
    result = await mediator.send(query)

    return QuoteServiceStatus(
        running=result.running,
        subscription_count=result.subscription_count,
        active_symbols=result.active_symbols,
    )
