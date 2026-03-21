"""Route for listing symbols."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from pocketquant.api.market_data.handlers.list_symbols.query import ListSymbolsQuery
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.get("/symbols")
async def list_symbols(
    mediator: FromDishka[Mediator],
    exchange: str | None = Query(default=None, description="Filter by exchange"),
) -> list[dict]:
    query = ListSymbolsQuery(exchange=exchange)
    return await mediator.send(query)
