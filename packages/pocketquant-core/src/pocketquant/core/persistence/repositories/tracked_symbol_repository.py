"""TrackedSymbolRepository — CRUD for the tracked_symbols collection."""

from datetime import UTC, datetime

from pocketquant.core.common.constants import COLLECTION_TRACKED_SYMBOLS
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.persistence.base_repository import BaseRepository


class TrackedSymbolRepository(BaseRepository):
    """Repository for tracked_symbols — composite ``symbol`` is the primary key."""

    _collection_name = COLLECTION_TRACKED_SYMBOLS

    async def list_all(self) -> list[TrackedSymbol]:
        """Return all tracked symbols sorted by composite symbol."""
        cursor = self._collection().find({}).sort([("symbol", 1)])
        return [TrackedSymbol.from_mongo(doc) async for doc in cursor]

    async def upsert(self, ts: TrackedSymbol) -> None:
        """Insert or update a tracked symbol. Idempotent."""
        collection = self._collection()
        doc = ts.to_mongo()
        doc_id = doc.pop("_id")
        created_at = doc.pop("created_at")
        doc["updated_at"] = datetime.now(UTC)

        await collection.update_one(
            {"symbol": ts.symbol},
            {
                "$set": doc,
                "$setOnInsert": {"_id": doc_id, "created_at": created_at},
            },
            upsert=True,
        )

    async def update(self, symbol: str, fields: dict) -> bool:
        """Update metadata fields for an existing tracked symbol. Returns True if found."""
        collection = self._collection()
        fields["updated_at"] = datetime.now(UTC)
        result = await collection.update_one(
            {"symbol": symbol},
            {"$set": fields},
        )
        return result.matched_count > 0

    async def delete(self, symbol: str) -> bool:
        """Remove a tracked symbol. Returns True if a document was deleted."""
        result = await self._collection().delete_one({"symbol": symbol})
        return result.deleted_count > 0

    async def exists(self, symbol: str) -> bool:
        """Return True if composite ``symbol`` is in the collection."""
        doc = await self._collection().find_one(
            {"symbol": symbol},
            {"_id": 1},
        )
        return doc is not None

    async def ensure_indexes(self) -> None:
        """Create unique index on composite ``symbol``."""
        await self._collection().create_index(
            [("symbol", 1)],
            unique=True,
            name="ix_tracked_symbols_symbol",
        )
