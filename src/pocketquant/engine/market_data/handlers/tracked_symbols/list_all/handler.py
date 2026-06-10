"""Handler for listing all tracked symbols."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.engine.market_data.handlers.tracked_symbols.list_all.query import (
    ListTrackedSymbolsQuery,
)


@handles(ListTrackedSymbolsQuery)
class ListTrackedSymbolsHandler(Handler[ListTrackedSymbolsQuery, list[dict]]):
    """Return all tracked composite symbols."""

    def __init__(self, tracked_symbol_repository: TrackedSymbolRepository) -> None:
        self._repo = tracked_symbol_repository

    async def handle(self, request: ListTrackedSymbolsQuery) -> list[dict]:
        symbols = await self._repo.list_all()
        return [
            {
                "symbol": ts.symbol,
                "created_at": ts.created_at.isoformat(),
                "seeded_from": ts.seeded_from,
            }
            for ts in symbols
        ]
