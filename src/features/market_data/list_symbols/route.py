"""Route for listing symbols."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query

from src.common.mediator import Mediator
from src.features.market_data.list_symbols.query import ListSymbolsQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/symbols")
async def list_symbols(
    mediator: FromDishka[Mediator],
    exchange: str | None = Query(default=None, description="Filter by exchange"),
) -> list[dict]:
    query = ListSymbolsQuery(exchange=exchange)
    return await mediator.send(query)
