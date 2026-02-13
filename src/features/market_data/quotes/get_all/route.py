"""API route for getting all active quotes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.quotes.get_all.query import GetAllQuotesQuery
from src.features.market_data.quotes.get_latest.route import QuoteResponse

router = APIRouter()


@router.get("/all", response_model=list[QuoteResponse])
async def get_all_quotes(
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> list[QuoteResponse]:
    query = GetAllQuotesQuery()
    results = await mediator.send(query)
    return [QuoteResponse.from_result(r) for r in results]
