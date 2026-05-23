"""Route for listing symbols."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.api.market_data.handlers.list_symbols.query import ListSymbolsQuery
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.get("/symbols")
async def list_symbols(
    mediator: FromDishka[Mediator],
) -> list[dict]:
    query = ListSymbolsQuery()
    return await mediator.send(query)
