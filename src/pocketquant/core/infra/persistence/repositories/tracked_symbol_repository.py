from datetime import UTC, datetime

from pocketquant.core.common.constants import COLLECTION_TRACKED_SYMBOLS
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.persistence.base_repository import SymbolScopedRepository


class TrackedSymbolRepository(SymbolScopedRepository):
    _collection_name = COLLECTION_TRACKED_SYMBOLS

    async def list_all(self) -> list[TrackedSymbol]:
        cursor = self._collection().find({}).sort([("symbol", 1)])
        return [TrackedSymbol.from_mongo(doc) async for doc in cursor]

    async def upsert(self, ts: TrackedSymbol) -> None:
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

    async def exists(self, symbol: str) -> bool:
        doc = await self._collection().find_one(
            {"symbol": symbol},
            {"_id": 1},
        )
        return doc is not None

    async def ensure_indexes(self) -> None:
        await self._collection().create_index(
            [("symbol", 1)],
            unique=True,
            name="ix_tracked_symbols_symbol",
        )
