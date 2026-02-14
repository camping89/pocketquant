"""Handler for list symbols query."""

from src.common.constants import COLLECTION_SYMBOLS
from src.common.database import Database
from src.common.mediator import Handler, handles
from src.features.market_data.list_symbols.query import ListSymbolsQuery


@handles(ListSymbolsQuery)
class ListSymbolsHandler(Handler[ListSymbolsQuery, list[dict]]):
    """Handle listing symbols from database."""

    async def handle(self, request: ListSymbolsQuery) -> list[dict]:
        collection = Database.get_collection(COLLECTION_SYMBOLS)

        query = {}
        if request.exchange:
            query["exchange"] = request.exchange.upper()

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
