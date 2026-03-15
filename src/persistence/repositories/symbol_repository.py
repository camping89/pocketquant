"""Symbol repository for MongoDB persistence."""

from datetime import UTC, datetime

from src.common.constants import COLLECTION_SYMBOLS
from src.domain.symbol import Symbol
from src.persistence.base_repository import BaseRepository


class SymbolRepository(BaseRepository):
    """Repository for symbol tracking."""

    _collection_name = COLLECTION_SYMBOLS

    async def upsert(self, symbol: Symbol) -> None:
        """Upsert symbol record."""
        collection = self._collection()
        doc = symbol.to_mongo()
        created_at = doc.pop("created_at", None)

        await collection.update_one(
            {"symbol": doc["symbol"], "exchange": doc["exchange"]},
            {"$set": doc, "$setOnInsert": {"created_at": created_at or datetime.now(UTC)}},
            upsert=True,
        )

    async def find_all(self, exchange: str | None = None) -> list[Symbol]:
        """Get all symbols, optionally filtered by exchange."""
        collection = self._collection()

        query = {}
        if exchange:
            query["exchange"] = exchange.upper()

        cursor = collection.find(query).sort("symbol", 1)

        return [Symbol.from_mongo(doc) async for doc in cursor]

    async def ensure_indexes(self) -> None:
        """Create compound index on (symbol, exchange)."""
        collection = self._collection()
        await collection.create_index(
            [("symbol", 1), ("exchange", 1)],
            unique=True,
            name="ix_symbols_symbol_exchange",
        )
