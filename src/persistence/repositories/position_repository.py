"""Position repository for MongoDB persistence."""

from src.common.constants import COLLECTION_POSITIONS
from src.domain.position import PositionAggregate
from src.persistence.base_repository import BaseRepository
from src.persistence.schemas.position_schema import PositionDocument


class PositionRepository(BaseRepository):
    """MongoDB repository for position persistence."""

    _collection_name = COLLECTION_POSITIONS

    async def save(self, position: PositionAggregate) -> None:
        """Save or update position."""
        doc = PositionDocument.from_aggregate(position)
        collection = self._collection()
        await collection.replace_one(
            {"_id": position.id}, doc.model_dump(by_alias=True), upsert=True
        )

    async def get(self, position_id: str) -> PositionAggregate | None:
        """Get position by ID."""
        collection = self._collection()
        doc = await collection.find_one({"_id": position_id})
        if not doc:
            return None
        return PositionDocument(**doc).to_aggregate()

    async def get_by_strategy(self, strategy_id: str) -> PositionAggregate | None:
        """Get open position for a strategy."""
        collection = self._collection()
        doc = await collection.find_one({"strategy_id": strategy_id, "is_closed": False})
        if not doc:
            return None
        return PositionDocument(**doc).to_aggregate()

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        """Get all open positions."""
        collection = self._collection()
        cursor = collection.find({"is_closed": False}).limit(limit)
        return [PositionDocument(**doc).to_aggregate() async for doc in cursor]

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient queries."""
        collection = self._collection()
        await collection.create_index("strategy_id")
        await collection.create_index("is_closed")
        await collection.create_index([("symbol", 1), ("exchange", 1)])
