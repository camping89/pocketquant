"""Symbol repository for MongoDB persistence."""

from datetime import UTC, datetime

from pocketquant.core.common.constants import COLLECTION_SYMBOLS
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.infra.persistence.base_repository import BaseRepository


class SymbolRepository(BaseRepository):
    """Repository for symbol tracking. ``symbol`` is composite ``{code}:{exchange}``."""

    _collection_name = COLLECTION_SYMBOLS

    async def upsert(self, symbol: Symbol) -> None:
        """Upsert symbol record by composite symbol identifier."""
        collection = self._collection()
        doc = symbol.to_mongo()
        symbol_id = doc.pop("_id", None)
        created_at = doc.pop("created_at", None)

        set_on_insert: dict = {}
        if created_at:
            set_on_insert["created_at"] = created_at
        if symbol_id:
            set_on_insert["_id"] = symbol_id

        await collection.update_one(
            {"symbol": doc["symbol"]},
            {"$set": doc, "$setOnInsert": set_on_insert or {"created_at": datetime.now(UTC)}},
            upsert=True,
        )

    async def touch(self, symbol: str) -> None:
        """Ensure a symbol document exists without overwriting its metadata.

        The sync pipeline calls this on every run. A full ``$set`` would reset
        asset_class / calendar_id / contract_spec to their crypto defaults, so a
        seeded futures symbol would silently become crypto on its first sync.
        """
        doc = Symbol.create(symbol=symbol).to_mongo()
        symbol_value = doc.pop("symbol")
        await self._collection().update_one(
            {"symbol": symbol_value},
            {"$setOnInsert": {**doc, "symbol": symbol_value}},
            upsert=True,
        )

    async def find_by_symbol(self, symbol: str) -> Symbol | None:
        """Look up one symbol record by composite identifier."""
        doc = await self._collection().find_one({"symbol": symbol.upper()})
        return Symbol.from_mongo(doc) if doc else None

    async def find_all(self) -> list[Symbol]:
        """Get all symbols, sorted by composite symbol."""
        collection = self._collection()
        cursor = collection.find({}).sort("symbol", 1)
        return [Symbol.from_mongo(doc) async for doc in cursor]

    async def ensure_indexes(self) -> None:
        """Create unique index on composite symbol."""
        collection = self._collection()
        await collection.create_index(
            [("symbol", 1)],
            unique=True,
            name="ix_symbols_symbol",
        )
