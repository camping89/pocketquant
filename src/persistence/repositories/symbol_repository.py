"""Symbol repository for MongoDB persistence."""

from datetime import UTC, datetime

from src.common.constants import COLLECTION_SYMBOLS
from src.persistence.base_repository import BaseRepository


class SymbolRepository(BaseRepository):
    """Repository for symbol tracking."""

    _collection_name = COLLECTION_SYMBOLS

    @staticmethod
    async def upsert(symbol: str, exchange: str) -> None:
        """Upsert symbol record."""
        collection = SymbolRepository._collection()
        symbol_doc = {
            "symbol": symbol,
            "exchange": exchange,
            "is_active": True,
            "updated_at": datetime.now(UTC),
        }
        await collection.update_one(
            {"symbol": symbol, "exchange": exchange},
            {"$set": symbol_doc, "$setOnInsert": {"created_at": datetime.now(UTC)}},
            upsert=True,
        )

    @staticmethod
    async def find_all(exchange: str | None = None) -> list[dict]:
        """Get all symbols, optionally filtered by exchange."""
        collection = SymbolRepository._collection()

        query = {}
        if exchange:
            query["exchange"] = exchange.upper()

        cursor = collection.find(query).sort("symbol", 1)

        return [
            {
                "symbol": doc["symbol"],
                "exchange": doc["exchange"],
                "name": doc.get("name"),
                "asset_type": doc.get("asset_type"),
                "is_active": doc.get("is_active", True),
            }
            async for doc in cursor
        ]

    @staticmethod
    async def ensure_indexes() -> None:
        """Create compound index on (symbol, exchange)."""
        collection = SymbolRepository._collection()
        await collection.create_index(
            [("symbol", 1), ("exchange", 1)],
            unique=True,
        )
