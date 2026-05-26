"""Order repository for MongoDB persistence."""

from pocketquant.core.common.constants import COLLECTION_ORDERS
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.persistence.base_repository import BaseRepository


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

    async def find_by_subscription(
        self, subscription_id: str, limit: int = 1000
    ) -> list[OrderAggregate]:
        """Get all orders for a subscription."""
        collection = self._collection()
        cursor = collection.find({"subscription_id": subscription_id}).limit(limit)
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
        await collection.create_index("subscription_id", name="ix_orders_subscription_id")
        await collection.create_index("status", name="ix_orders_status")
        await collection.create_index("symbol", name="ix_orders_symbol")
