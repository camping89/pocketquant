"""Order repository for MongoDB persistence."""

from src.common.constants import COLLECTION_ORDERS
from src.domain.order import OrderAggregate
from src.persistence.base_repository import BaseRepository
from src.persistence.schemas.order_schema import OrderDocument


class OrderRepository(BaseRepository):
    """MongoDB repository for order persistence."""

    _collection_name = COLLECTION_ORDERS

    @staticmethod
    async def save(order: OrderAggregate) -> None:
        """Save or update order."""
        doc = OrderDocument.from_aggregate(order)
        collection = OrderRepository._collection()
        await collection.replace_one(
            {"_id": order.id}, doc.model_dump(by_alias=True), upsert=True
        )

    @staticmethod
    async def get(order_id: str) -> OrderAggregate | None:
        """Get order by ID."""
        collection = OrderRepository._collection()
        doc = await collection.find_one({"_id": order_id})
        if not doc:
            return None
        return OrderDocument(**doc).to_aggregate()

    @staticmethod
    async def find_by_strategy(strategy_id: str) -> list[OrderAggregate]:
        """Get all orders for a strategy."""
        collection = OrderRepository._collection()
        cursor = collection.find({"strategy_id": strategy_id})
        return [OrderDocument(**doc).to_aggregate() async for doc in cursor]

    @staticmethod
    async def find_pending() -> list[OrderAggregate]:
        """Get all pending orders."""
        collection = OrderRepository._collection()
        cursor = collection.find({"status": {"$in": ["pending", "submitted", "partially_filled"]}})
        return [OrderDocument(**doc).to_aggregate() async for doc in cursor]

    @staticmethod
    async def ensure_indexes() -> None:
        """Create indexes for efficient queries."""
        collection = OrderRepository._collection()
        await collection.create_index("strategy_id")
        await collection.create_index("status")
        await collection.create_index([("symbol", 1), ("exchange", 1)])
