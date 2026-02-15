"""Handler for list symbols query."""

from src.common.mediator import Handler, handles
from src.features.market_data.list_symbols.query import ListSymbolsQuery
from src.persistence.repositories.symbol_repository import SymbolRepository


@handles(ListSymbolsQuery)
class ListSymbolsHandler(Handler[ListSymbolsQuery, list[dict]]):
    """Handle listing symbols from database."""

    def __init__(self, symbol_repository: SymbolRepository):
        self._symbol_repo = symbol_repository

    async def handle(self, request: ListSymbolsQuery) -> list[dict]:
        symbols = await self._symbol_repo.find_all(exchange=request.exchange)
        return [
            {
                "symbol": s.symbol,
                "exchange": s.exchange,
                "name": s.name,
                "asset_type": s.asset_type,
                "is_active": s.is_active,
            }
            for s in symbols
        ]
