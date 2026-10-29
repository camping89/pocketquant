from __future__ import annotations

from pocketquant.core.common.logging import get_logger
from pocketquant.core.infra.persistence.mongodb import Database

logger = get_logger(__name__)


class BaseRepository:
    _collection_name: str

    def __init__(self, database: Database) -> None:
        self._database = database

    def _collection(self):
        return self._database.get_collection(self._collection_name)


# A document matching any of _symbol_fields belongs to that symbol.
class SymbolScopedRepository(BaseRepository):
    _symbol_fields: tuple[str, ...] = ("symbol",)

    async def delete_by_symbol(self, symbol: str) -> int:
        query = {"$or": [{field: symbol} for field in self._symbol_fields]}
        result = await self._collection().delete_many(query)
        logger.info(
            "repository.deleted_by_symbol",
            collection=self._collection_name,
            symbol=symbol,
            count=result.deleted_count,
        )
        return result.deleted_count
