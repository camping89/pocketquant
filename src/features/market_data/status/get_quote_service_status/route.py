"""Route for getting quote service status."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.status.get_quote_service_status.query import (
    GetQuoteServiceStatusQuery,
)


class QuoteServiceStatus(BaseModel):
    running: bool
    subscription_count: int
    active_symbols: list[str]


router = APIRouter()


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
