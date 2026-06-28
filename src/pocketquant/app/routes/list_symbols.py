from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.engine.market_data.symbols_service import ListSymbolsQuery, SymbolQueryService

router = APIRouter(route_class=DishkaRoute)


@router.get("/symbols")
async def list_symbols(
    symbol_service: FromDishka[SymbolQueryService],
) -> list[dict]:
    query = ListSymbolsQuery()
    return await symbol_service.list_symbols(query)
