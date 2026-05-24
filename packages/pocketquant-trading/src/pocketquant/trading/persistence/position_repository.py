"""Position repository for MongoDB persistence."""

from pocketquant.core.common.constants import COLLECTION_POSITIONS
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.persistence.base_repository import BaseRepository


class PositionRepository(BaseRepository):
    """MongoDB repository for position persistence."""

    _collection_name = COLLECTION_POSITIONS

    async def save(self, position: PositionAggregate) -> None:
        """Save or update position."""
        collection = self._collection()
        await collection.replace_one({"_id": position.id}, position.to_mongo(), upsert=True)

    async def get(self, position_id: str) -> PositionAggregate | None:
        """Get position by ID."""
        collection = self._collection()
        doc = await collection.find_one({"_id": position_id})
        if not doc:
            return None
        return PositionAggregate.from_mongo(doc)

    async def get_by_strategy(self, strategy_id: str) -> PositionAggregate | None:
        """Get open position for a strategy."""
        collection = self._collection()
        doc = await collection.find_one({"strategy_id": strategy_id, "is_closed": False})
        if not doc:
            return None
        return PositionAggregate.from_mongo(doc)

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        """Get all open positions."""
        collection = self._collection()
        cursor = collection.find({"is_closed": False}).limit(limit)
        return [PositionAggregate.from_mongo(doc) async for doc in cursor]

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient queries."""
        collection = self._collection()
        await collection.create_index("strategy_id", name="ix_positions_strategy_id")
        await collection.create_index("is_closed", name="ix_positions_is_closed")
        await collection.create_index("symbol", name="ix_positions_symbol")
