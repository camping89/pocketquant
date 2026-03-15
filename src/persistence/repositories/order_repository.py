"""Order repository for MongoDB persistence."""

from src.common.constants import COLLECTION_ORDERS
from src.domain.order import OrderAggregate
from src.persistence.base_repository import BaseRepository


class OrderRepository(BaseRepository):
    """MongoDB repository for order persistence."""

    _collection_name = COLLECTION_ORDERS

    async def save(self, order: OrderAggregate) -> None:
        """Save or update order."""
        collection = self._collection()
        await collection.replace_one({"_id": order.id}, order.to_mongo(), upsert=True)

    async def get(self, order_id: str) -> OrderAggregate | None:
        """Get order by ID."""
        collection = self._collection()
        doc = await collection.find_one({"_id": order_id})
        if not doc:
            return None
        return OrderAggregate.from_mongo(doc)

    async def find_by_strategy(self, strategy_id: str, limit: int = 1000) -> list[OrderAggregate]:
        """Get all orders for a strategy."""
        collection = self._collection()
        cursor = collection.find({"strategy_id": strategy_id}).limit(limit)
        return [OrderAggregate.from_mongo(doc) async for doc in cursor]

    async def find_pending(self, limit: int = 500) -> list[OrderAggregate]:
        """Get all pending orders."""
        collection = self._collection()
        cursor = collection.find(
            {"status": {"$in": ["pending", "submitted", "partially_filled"]}}
        ).limit(limit)
        return [OrderAggregate.from_mongo(doc) async for doc in cursor]

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient queries."""
        collection = self._collection()
        await collection.create_index("strategy_id", name="ix_orders_strategy_id")
        await collection.create_index("status", name="ix_orders_status")
        await collection.create_index(
            [("symbol", 1), ("exchange", 1)],
            name="ix_orders_symbol_exchange",
        )
