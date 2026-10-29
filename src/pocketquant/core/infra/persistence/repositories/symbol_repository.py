from datetime import UTC, datetime

from pocketquant.core.common.constants import COLLECTION_SYMBOLS
from pocketquant.core.domain.market_data.provider_routing_domain_service import unseeded_symbol
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.infra.persistence.base_repository import SymbolScopedRepository


class SymbolRepository(SymbolScopedRepository):
    _collection_name = COLLECTION_SYMBOLS

    async def upsert(self, symbol: Symbol) -> None:
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

    # Sync calls this on every run. A full $set would reset asset_class, calendar_id and
    # contract_spec to provider defaults, so a seeded symbol would lose its metadata.
    async def touch(self, symbol: str) -> None:
        doc = unseeded_symbol(symbol).to_mongo()
        symbol_value = doc.pop("symbol")
        await self._collection().update_one(
            {"symbol": symbol_value},
            {"$setOnInsert": {**doc, "symbol": symbol_value}},
            upsert=True,
        )

    async def find_by_symbol(self, symbol: str) -> Symbol | None:
        doc = await self._collection().find_one({"symbol": symbol.upper()})
        return Symbol.from_mongo(doc) if doc else None

    async def find_all(self) -> list[Symbol]:
        collection = self._collection()
        cursor = collection.find({}).sort("symbol", 1)
        return [Symbol.from_mongo(doc) async for doc in cursor]

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index(
            [("symbol", 1)],
            unique=True,
            name="ix_symbols_symbol",
        )
