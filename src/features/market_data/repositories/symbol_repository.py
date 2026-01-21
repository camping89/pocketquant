from datetime import UTC, datetime

from pymongo.asynchronous.collection import AsyncCollection

from src.common.database import Database
from src.common.logging import get_logger
from src.features.market_data.models.symbol import Symbol, SymbolCreate

logger = get_logger(__name__)


class SymbolRepository:
    COLLECTION_NAME = "symbols"

    @classmethod
    def _get_collection(cls) -> AsyncCollection:
        return Database.get_collection(cls.COLLECTION_NAME)

    @classmethod
    async def upsert(cls, symbol_data: SymbolCreate) -> Symbol:
        collection = cls._get_collection()

        symbol = Symbol(**symbol_data.model_dump())
        doc = symbol.to_mongo()
        doc["updated_at"] = datetime.now(UTC)

        created_at = doc.pop("created_at", None)

        await collection.update_one(
            {
                "symbol": doc["symbol"],
                "exchange": doc["exchange"],
            },
            {"$set": doc, "$setOnInsert": {"created_at": created_at or datetime.now(UTC)}},
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
        collection = cls._get_collection()

        result = await collection.delete_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
            }
        )

        return result.deleted_count > 0
