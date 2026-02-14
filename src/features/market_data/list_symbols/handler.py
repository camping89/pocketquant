"""Handler for list symbols query."""

from src.common.mediator import Handler, handles
from src.features.market_data.list_symbols.query import ListSymbolsQuery
from src.persistence.repositories.symbol_repository import SymbolRepository


@handles(ListSymbolsQuery)
class ListSymbolsHandler(Handler[ListSymbolsQuery, list[dict]]):
    """Handle listing symbols from database."""

    async def handle(self, request: ListSymbolsQuery) -> list[dict]:
        return await SymbolRepository.find_all(exchange=request.exchange)
