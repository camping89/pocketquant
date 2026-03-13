"""Route for getting quote service status."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pydantic import BaseModel

from src.common.mediator import Mediator
from src.features.market_data.status.get_quote_service_status.query import (
    GetQuoteServiceStatusQuery,
)


class QuoteServiceStatus(BaseModel):
    running: bool
    subscription_count: int
    active_symbols: list[str]


router = APIRouter(route_class=DishkaRoute)


@router.get("/status", response_model=QuoteServiceStatus)
async def get_quote_service_status(
    mediator: FromDishka[Mediator],
) -> QuoteServiceStatus:
    query = GetQuoteServiceStatusQuery()
    result = await mediator.send(query)

    return QuoteServiceStatus(
        running=result.running,
        subscription_count=result.subscription_count,
        active_symbols=result.active_symbols,
    )
