"""Handler for list symbols query."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.engine.market_data.handlers.list_symbols.query import ListSymbolsQuery


@handles(ListSymbolsQuery)
class ListSymbolsHandler(Handler[ListSymbolsQuery, list[dict]]):
    def __init__(self, symbol_repository: SymbolRepository):
        self._symbol_repo = symbol_repository

    async def handle(self, request: ListSymbolsQuery) -> list[dict]:
        symbols = await self._symbol_repo.find_all()
        return [
            {
                "symbol": s.symbol,
                "name": s.name,
                "asset_type": s.asset_type,
                "is_active": s.is_active,
            }
            for s in symbols
        ]
