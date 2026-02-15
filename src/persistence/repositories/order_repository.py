"""Order repository for MongoDB persistence."""

from src.common.constants import COLLECTION_ORDERS
from src.domain.order import OrderAggregate
from src.persistence.base_repository import BaseRepository
from src.persistence.schemas.order_schema import OrderDocument


class OrderRepository(BaseRepository):
    """MongoDB repository for order persistence."""

    _collection_name = COLLECTION_ORDERS

    async def save(self, order: OrderAggregate) -> None:
        """Save or update order."""
        doc = OrderDocument.from_aggregate(order)
        collection = self._collection()
        await collection.replace_one({"_id": order.id}, doc.model_dump(by_alias=True), upsert=True)

    async def get(self, order_id: str) -> OrderAggregate | None:
        """Get order by ID."""
        collection = self._collection()
        doc = await collection.find_one({"_id": order_id})
        if not doc:
            return None
        return OrderDocument(**doc).to_aggregate()

    async def find_by_strategy(self, strategy_id: str, limit: int = 1000) -> list[OrderAggregate]:
        """Get all orders for a strategy."""
        collection = self._collection()
        cursor = collection.find({"strategy_id": strategy_id}).limit(limit)
        return [OrderDocument(**doc).to_aggregate() async for doc in cursor]

    async def find_pending(self, limit: int = 500) -> list[OrderAggregate]:
        """Get all pending orders."""
        collection = self._collection()
        cursor = collection.find({"status": {"$in": ["pending", "submitted", "partially_filled"]}}).limit(limit)
        return [OrderDocument(**doc).to_aggregate() async for doc in cursor]

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient queries."""
        collection = self._collection()
        await collection.create_index("strategy_id")
        await collection.create_index("status")
        await collection.create_index([("symbol", 1), ("exchange", 1)])
