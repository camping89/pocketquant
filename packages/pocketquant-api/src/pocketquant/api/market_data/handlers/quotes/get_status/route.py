"""Route for GET /api/v1/market-data/quotes/status."""

from datetime import datetime

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.api.market_data.handlers.quotes.get_status.query import GetQuotesStatusQuery
from pocketquant.core.common.mediator import Mediator
from pydantic import BaseModel


class QuotesStatusResponse(BaseModel):
    connected: bool
    subscribed_count: int
    last_tick_at: datetime | None = None
    lag_seconds: float | None = None


router = APIRouter(route_class=DishkaRoute)


@router.get("/status", response_model=QuotesStatusResponse, tags=["Real-time Quotes"])
async def get_quotes_status(
    mediator: FromDishka[Mediator],
) -> QuotesStatusResponse:
    """Return WS feed health: connection state, subscription count, last tick lag."""
    result = await mediator.send(GetQuotesStatusQuery())
    return QuotesStatusResponse(
        connected=result.connected,
        subscribed_count=result.subscribed_count,
        last_tick_at=result.last_tick_at,
        lag_seconds=result.lag_seconds,
    )
