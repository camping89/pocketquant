"""Position repository for MongoDB persistence."""

from src.common.constants import COLLECTION_POSITIONS
from src.common.database import Database
from src.domain.position import PositionAggregate
from src.features.trading.base.models import PositionDocument


class PositionRepository:
    """MongoDB repository for position persistence."""

    @staticmethod
    async def save(position: PositionAggregate) -> None:
        """Save or update position."""
        doc = PositionDocument.from_aggregate(position)
        collection = Database.get_collection(COLLECTION_POSITIONS)
        await collection.replace_one(
            {"_id": position.id}, doc.model_dump(by_alias=True), upsert=True
        )

    @staticmethod
    async def get(position_id: str) -> PositionAggregate | None:
        """Get position by ID."""
        collection = Database.get_collection(COLLECTION_POSITIONS)
        doc = await collection.find_one({"_id": position_id})
        if not doc:
            return None
        return PositionDocument(**doc).to_aggregate()

    @staticmethod
    async def get_by_strategy(strategy_id: str) -> PositionAggregate | None:
        """Get open position for a strategy."""
        collection = Database.get_collection(COLLECTION_POSITIONS)
        doc = await collection.find_one({"strategy_id": strategy_id, "is_closed": False})
        if not doc:
            return None
        return PositionDocument(**doc).to_aggregate()

    @staticmethod
    async def find_open() -> list[PositionAggregate]:
        """Get all open positions."""
        collection = Database.get_collection(COLLECTION_POSITIONS)
        cursor = collection.find({"is_closed": False})
        return [PositionDocument(**doc).to_aggregate() async for doc in cursor]

    @staticmethod
    async def ensure_indexes() -> None:
        """Create indexes for efficient queries."""
        collection = Database.get_collection(COLLECTION_POSITIONS)
        await collection.create_index("strategy_id")
        await collection.create_index("is_closed")
        await collection.create_index([("symbol", 1), ("exchange", 1)])
