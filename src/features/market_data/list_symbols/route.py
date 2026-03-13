"""Route for listing symbols."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.common.mediator import Mediator
from src.dependencies import get_mediator
from src.features.market_data.list_symbols.query import ListSymbolsQuery

router = APIRouter()


@router.get("/symbols")
async def list_symbols(
    mediator: Annotated[Mediator, Depends(get_mediator)],
    exchange: str | None = Query(default=None, description="Filter by exchange"),
) -> list[dict]:
    query = ListSymbolsQuery(exchange=exchange)
    return await mediator.send(query)
