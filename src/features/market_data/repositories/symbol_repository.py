"""Repository for symbol metadata."""

from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorCollection

from src.common.database import Database
from src.common.logging import get_logger
from src.features.market_data.models.symbol import Symbol, SymbolCreate

logger = get_logger(__name__)


class SymbolRepository:
    """Repository for symbol metadata operations."""

    COLLECTION_NAME = "symbols"

    @classmethod
    def _get_collection(cls) -> AsyncIOMotorCollection:
        """Get the symbols collection."""
        return Database.get_collection(cls.COLLECTION_NAME)

    @classmethod
    async def upsert(cls, symbol_data: SymbolCreate) -> Symbol:
        """Upsert a symbol record.

        Args:
            symbol_data: Symbol data to upsert.

        Returns:
            The upserted Symbol.
        """
        collection = cls._get_collection()

        symbol = Symbol(**symbol_data.model_dump())
        doc = symbol.to_mongo()
        doc["updated_at"] = datetime.utcnow()

        # Remove created_at from $set to avoid conflict with $setOnInsert
        created_at = doc.pop("created_at", None)

        await collection.update_one(
            {
                "symbol": doc["symbol"],
                "exchange": doc["exchange"],
            },
            {"$set": doc, "$setOnInsert": {"created_at": created_at or datetime.utcnow()}},
            upsert=True,
        )

        logger.debug(
            "symbol_upserted",
            symbol=symbol.symbol,
            exchange=symbol.exchange,
        )

        return symbol

    @classmethod
    async def get(cls, symbol: str, exchange: str) -> Symbol | None:
        """Get a symbol by symbol and exchange.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.

        Returns:
            Symbol if found, None otherwise.
        """
        collection = cls._get_collection()

        doc = await collection.find_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
            }
        )

        if doc:
            return Symbol.from_mongo(doc)
        return None

    @classmethod
    async def get_all(cls, exchange: str | None = None) -> list[Symbol]:
        """Get all symbols, optionally filtered by exchange.

        Args:
            exchange: Optional exchange filter.

        Returns:
            List of symbols.
        """
        collection = cls._get_collection()

        query = {}
        if exchange:
            query["exchange"] = exchange.upper()

        cursor = collection.find(query).sort("symbol", 1)

        symbols = []
        async for doc in cursor:
            symbols.append(Symbol.from_mongo(doc))

        return symbols

    @classmethod
    async def delete(cls, symbol: str, exchange: str) -> bool:
        """Delete a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.

        Returns:
            True if deleted, False if not found.
        """
        collection = cls._get_collection()

        result = await collection.delete_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
            }
        )

        return result.deleted_count > 0
