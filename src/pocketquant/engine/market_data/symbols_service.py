"""Symbol query service — list all known symbols from the symbol repository."""

from pydantic import BaseModel

from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository


class ListSymbolsQuery(BaseModel):
    """Query to list all known symbols."""

    pass


class SymbolQueryService:
    """List all symbols that have had OHLCV data synced."""

    def __init__(self, symbol_repository: SymbolRepository) -> None:
        self._symbol_repo = symbol_repository

    async def list_symbols(self, request: ListSymbolsQuery) -> list[dict]:
        """Return all known symbols with basic metadata."""
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
