"""Position repository for MongoDB persistence."""

from pocketquant.core.common.constants import COLLECTION_POSITIONS
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.persistence.base_repository import BaseRepository


class PositionRepository(BaseRepository):
    _collection_name = COLLECTION_POSITIONS

    async def save(self, position: PositionAggregate) -> None:
        collection = self._collection()
        await collection.replace_one({"_id": position.id}, position.to_mongo(), upsert=True)

    async def get(self, position_id: str) -> PositionAggregate | None:
        collection = self._collection()
        doc = await collection.find_one({"_id": position_id})
        if not doc:
            return None
        return PositionAggregate.from_mongo(doc)

    async def get_by_subscription(self, subscription_id: str) -> PositionAggregate | None:
        collection = self._collection()
        doc = await collection.find_one({"subscription_id": subscription_id, "is_closed": False})
        if not doc:
            return None
        return PositionAggregate.from_mongo(doc)

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        collection = self._collection()
        cursor = collection.find({"is_closed": False}).limit(limit)
        return [PositionAggregate.from_mongo(doc) async for doc in cursor]

    async def find_open_by_subscription(
        self, subscription_id: str, limit: int = 50
    ) -> list[PositionAggregate]:
        """Return all open positions for a subscription (typically 0 or 1)."""
        collection = self._collection()
        cursor = collection.find({"subscription_id": subscription_id, "is_closed": False}).limit(
            limit
        )
        return [PositionAggregate.from_mongo(doc) async for doc in cursor]

    async def find_closed_by_subscription(
        self, subscription_id: str, limit: int = 100
    ) -> list[PositionAggregate]:
        """Return most-recently closed positions for a subscription, newest first."""
        collection = self._collection()
        cursor = (
            collection.find({"subscription_id": subscription_id, "is_closed": True})
            .sort("closed_at", -1)
            .limit(limit)
        )
        return [PositionAggregate.from_mongo(doc) async for doc in cursor]

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index("subscription_id", name="ix_positions_subscription_id")
        await collection.create_index("is_closed", name="ix_positions_is_closed")
        await collection.create_index("symbol", name="ix_positions_symbol")
