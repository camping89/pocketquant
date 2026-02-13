"""Order repository for MongoDB persistence."""

from src.common.constants import COLLECTION_ORDERS
from src.common.database import Database
from src.domain.order import OrderAggregate
from src.features.trading.base.models import OrderDocument


class OrderRepository:
    """MongoDB repository for order persistence."""

    @staticmethod
    async def save(order: OrderAggregate) -> None:
        """Save or update order."""
        doc = OrderDocument.from_aggregate(order)
        collection = Database.get_collection(COLLECTION_ORDERS)
        await collection.replace_one(
            {"_id": order.id}, doc.model_dump(by_alias=True), upsert=True
        )

    @staticmethod
    async def get(order_id: str) -> OrderAggregate | None:
        """Get order by ID."""
        collection = Database.get_collection(COLLECTION_ORDERS)
        doc = await collection.find_one({"_id": order_id})
        if not doc:
            return None
        return OrderDocument(**doc).to_aggregate()

    @staticmethod
    async def find_by_strategy(strategy_id: str) -> list[OrderAggregate]:
        """Get all orders for a strategy."""
        collection = Database.get_collection(COLLECTION_ORDERS)
        cursor = collection.find({"strategy_id": strategy_id})
        return [OrderDocument(**doc).to_aggregate() async for doc in cursor]

    @staticmethod
    async def find_pending() -> list[OrderAggregate]:
        """Get all pending orders."""
        collection = Database.get_collection(COLLECTION_ORDERS)
        cursor = collection.find({"status": {"$in": ["pending", "submitted", "partially_filled"]}})
        return [OrderDocument(**doc).to_aggregate() async for doc in cursor]

    @staticmethod
    async def ensure_indexes() -> None:
        """Create indexes for efficient queries."""
        collection = Database.get_collection(COLLECTION_ORDERS)
        await collection.create_index("strategy_id")
        await collection.create_index("status")
        await collection.create_index([("symbol", 1), ("exchange", 1)])
