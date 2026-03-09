"""Symbol repository for MongoDB persistence."""

from datetime import UTC, datetime

from src.common.constants import COLLECTION_SYMBOLS
from src.domain.symbol import SymbolAggregate
from src.domain.symbol.value_objects import SymbolInfo
from src.persistence.base_repository import BaseRepository
from src.persistence.schemas.symbol_schema import SymbolCreate


def _doc_to_aggregate(doc: dict) -> SymbolAggregate:
    """Convert a MongoDB document to a domain SymbolAggregate."""
    info = SymbolInfo(
        code=doc.get("symbol", ""),
        exchange=doc.get("exchange", ""),
        name=doc.get("name"),
        asset_type=doc.get("asset_type"),
        is_active=doc.get("is_active", True),
    )
    return SymbolAggregate(info=info)


class SymbolRepository(BaseRepository):
    """Repository for symbol tracking."""

    _collection_name = COLLECTION_SYMBOLS

    async def upsert(self, symbol_create: SymbolCreate) -> None:
        """Upsert symbol record."""
        collection = self._collection()
        symbol_doc = {
            "symbol": symbol_create.symbol.upper(),
            "exchange": symbol_create.exchange.upper(),
            "is_active": symbol_create.is_active,
            "updated_at": datetime.now(UTC),
        }
        if symbol_create.name:
            symbol_doc["name"] = symbol_create.name
        if symbol_create.asset_type:
            symbol_doc["asset_type"] = symbol_create.asset_type
        if symbol_create.currency:
            symbol_doc["currency"] = symbol_create.currency

        await collection.update_one(
            {"symbol": symbol_create.symbol.upper(), "exchange": symbol_create.exchange.upper()},
            {"$set": symbol_doc, "$setOnInsert": {"created_at": datetime.now(UTC)}},
            upsert=True,
        )

    async def find_all(self, exchange: str | None = None) -> list[SymbolAggregate]:
        """Get all symbols, optionally filtered by exchange."""
        collection = self._collection()

        query = {}
        if exchange:
            query["exchange"] = exchange.upper()

        cursor = collection.find(query).sort("symbol", 1)

        return [_doc_to_aggregate(doc) async for doc in cursor]

    async def ensure_indexes(self) -> None:
        """Create compound index on (symbol, exchange)."""
        collection = self._collection()
        await collection.create_index(
            [("symbol", 1), ("exchange", 1)],
            unique=True,
            name="ix_symbols_symbol_exchange",
        )
