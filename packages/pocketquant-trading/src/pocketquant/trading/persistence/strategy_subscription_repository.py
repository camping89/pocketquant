"""StrategySubscriptionRepository — MongoDB persistence for strategy subscriptions."""

from pymongo.errors import DuplicateKeyError

from pocketquant.core.common.logging import get_logger
from pocketquant.core.persistence.base_repository import BaseRepository
from pocketquant.trading.domain.subscription import (
    StrategySubscription,
    SubscriptionAlreadyExistsError,
)

logger = get_logger(__name__)


class StrategySubscriptionRepository(BaseRepository):
    """MongoDB repository for StrategySubscription persistence.

    Collection: strategy_subscriptions
    PK: _id = deterministic_id(strategy_id, symbol, exchange, interval)
    """

    _collection_name = "strategy_subscriptions"

    async def add(self, sub: StrategySubscription) -> None:
        """Insert a new subscription. Raises SubscriptionAlreadyExistsError if duplicate."""
        collection = self._collection()
        try:
            await collection.insert_one(sub.to_mongo())
            logger.debug("subscription_added", sub_id=sub.id, strategy_id=sub.strategy_id)
        except DuplicateKeyError:
            raise SubscriptionAlreadyExistsError(sub.id)

    async def get(self, sub_id: str) -> StrategySubscription | None:
        """Return a subscription by its deterministic ID, or None if not found."""
        collection = self._collection()
        doc = await collection.find_one({"_id": sub_id})
        if not doc:
            return None
        return StrategySubscription.from_mongo(doc)

    async def list_by_strategy(self, strategy_id: str) -> list[StrategySubscription]:
        """Return all subscriptions for a given strategy."""
        collection = self._collection()
        cursor = collection.find({"strategy_id": strategy_id})
        return [StrategySubscription.from_mongo(doc) async for doc in cursor]

    async def delete(self, sub_id: str) -> int:
        """Delete a subscription by ID. Returns deleted_count (0 or 1)."""
        collection = self._collection()
        result = await collection.delete_one({"_id": sub_id})
        logger.debug("subscription_deleted", sub_id=sub_id, count=result.deleted_count)
        return result.deleted_count

    async def delete_by_strategy(self, strategy_id: str) -> int:
        """Delete all subscriptions for a strategy. Returns deleted_count."""
        collection = self._collection()
        result = await collection.delete_many({"strategy_id": strategy_id})
        logger.debug(
            "subscriptions_deleted_by_strategy",
            strategy_id=strategy_id,
            count=result.deleted_count,
        )
        return result.deleted_count

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient by-strategy queries."""
        collection = self._collection()
        await collection.create_index(
            "strategy_id",
            name="ix_strategy_subscriptions_strategy_id",
        )
        logger.info("strategy_subscription_indexes_created")
