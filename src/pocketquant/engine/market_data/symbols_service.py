from pydantic import BaseModel

from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository


class ListSymbolsQuery(BaseModel):
    pass


class SymbolQueryService:
    def __init__(self, symbol_repository: SymbolRepository) -> None:
        self._symbol_repo = symbol_repository

    async def list_symbols(self, request: ListSymbolsQuery) -> list[dict]:
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
