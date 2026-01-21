from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.common.logging import get_logger
from src.config import Settings, get_settings
from src.features.market_data.models.ohlcv import Interval
from src.features.market_data.models.quote import Quote
from src.features.market_data.services.quote_service import QuoteService, get_quote_service

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
    def from_quote(cls, quote: Quote) -> QuoteResponse:
        return cls(
            symbol=quote.symbol,
            exchange=quote.exchange,
            timestamp=quote.timestamp.isoformat(),
            last_price=quote.last_price,
            bid=quote.bid,
            ask=quote.ask,
            volume=quote.volume,
            change=quote.change,
            change_percent=quote.change_percent,
            open_price=quote.open_price,
            high_price=quote.high_price,
            low_price=quote.low_price,
        )


class QuoteServiceStatus(BaseModel):
    running: bool
    subscription_count: int
    active_symbols: list[str]


def get_service(settings: Annotated[Settings, Depends(get_settings)]) -> QuoteService:
    return get_quote_service(settings)


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_to_symbol(
    request: SubscribeRequest,
    service: Annotated[QuoteService, Depends(get_service)],
) -> SubscribeResponse:
    if not service.is_running():
        raise HTTPException(
            status_code=400,
            detail="Quote service not running. Start it first via POST /quotes/start",
        )

    key = await service.subscribe(request.symbol, request.exchange)

    return SubscribeResponse(
        subscription_key=key,
        message=f"Subscribed to {key}",
    )


@router.post("/unsubscribe")
async def unsubscribe_from_symbol(
    request: SubscribeRequest,
    service: Annotated[QuoteService, Depends(get_service)],
) -> dict:
    await service.unsubscribe(request.symbol, request.exchange)

    return {
        "message": f"Unsubscribed from {request.exchange}:{request.symbol}".upper(),
    }


@router.get("/latest/{exchange}/{symbol}", response_model=QuoteResponse)
async def get_latest_quote(
    exchange: str,
    symbol: str,
    service: Annotated[QuoteService, Depends(get_service)],
) -> QuoteResponse:
    quote = await service.get_latest_quote(symbol, exchange)

    if quote is None:
        raise HTTPException(
            status_code=404,
            detail=f"No quote found for {exchange}:{symbol}. Make sure you're subscribed.",
        )

    return QuoteResponse.from_quote(quote)


@router.get("/all", response_model=list[QuoteResponse])
async def get_all_quotes(
    service: Annotated[QuoteService, Depends(get_service)],
) -> list[QuoteResponse]:
    quotes = await service.get_all_quotes()
    return [QuoteResponse.from_quote(q) for q in quotes]


@router.get("/current-bar/{exchange}/{symbol}")
async def get_current_bar(
    exchange: str,
    symbol: str,
    service: Annotated[QuoteService, Depends(get_service)],
    interval: Interval = Query(default=Interval.MINUTE_1),
) -> dict:
    aggregator = service.get_aggregator()
    bar = await aggregator.get_current_bar(symbol, exchange, interval)

    if bar is None:
        raise HTTPException(
            status_code=404,
            detail=f"No current bar for {exchange}:{symbol} at {interval.value}",
        )

    return bar


@router.post("/start")
async def start_quote_service(
    service: Annotated[QuoteService, Depends(get_service)],
) -> dict:
    if service.is_running():
        return {"status": "already_running", "message": "Quote service is already running"}

    await service.start()

    return {"status": "started", "message": "Quote service started"}


@router.post("/stop")
async def stop_quote_service(
    service: Annotated[QuoteService, Depends(get_service)],
) -> dict:
    if not service.is_running():
        return {"status": "not_running", "message": "Quote service is not running"}

    aggregator = service.get_aggregator()
    saved_count = await aggregator.flush_all_bars()

    await service.stop()

    return {
        "status": "stopped",
        "message": "Quote service stopped",
        "bars_saved": saved_count,
    }


@router.get("/status", response_model=QuoteServiceStatus)
async def get_quote_service_status(
    service: Annotated[QuoteService, Depends(get_service)],
) -> QuoteServiceStatus:
    aggregator = service.get_aggregator()

    return QuoteServiceStatus(
        running=service.is_running(),
        subscription_count=service.subscription_count,
        active_symbols=aggregator.active_symbols,
    )
