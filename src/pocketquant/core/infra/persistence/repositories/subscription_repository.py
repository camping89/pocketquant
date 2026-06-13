"""SubscriptionRepository — MongoDB persistence for strategy subscriptions."""

from pymongo.errors import DuplicateKeyError

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.subscription import (
    RunState,
    Subscription,
    SubscriptionAlreadyExistsError,
)
from pocketquant.core.infra.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class SubscriptionRepository(BaseRepository):
    """MongoDB repository for Subscription persistence.

    Collection: subscriptions (legacy name "strategy_subscriptions" is migrated at boot
    by ``migrate_strategy_id_fields`` in ``api.main_extensions``).
    PK: _id = uuid7 string; dedup of (strategy_code, symbol, interval) is enforced
    by the unique compound index ``ix_subscriptions_dedup_triple``.
    """

    _collection_name = "subscriptions"

    async def add(self, sub: Subscription) -> None:
        """Insert a new subscription. Raises SubscriptionAlreadyExistsError if duplicate.

        DuplicateKeyError comes from the compound triple index — two adds of the
        same triple carry different uuid7 ids yet still collide at the DB layer.
        """
        collection = self._collection()
        try:
            await collection.insert_one(sub.to_mongo())
            logger.debug(
                "subscription_added", sub_id=str(sub.id), strategy_code=sub.strategy_code
            )
        except DuplicateKeyError:
            raise SubscriptionAlreadyExistsError(
                sub.strategy_code, sub.symbol, sub.interval.value
            ) from None

    async def get(self, sub_id: str) -> Subscription | None:
        """Return a subscription by its uuid7 ID string, or None if not found."""
        collection = self._collection()
        doc = await collection.find_one({"_id": sub_id})
        if not doc:
            return None
        return Subscription.from_mongo(doc)

    async def list_by_strategy_code(self, strategy_code: str) -> list[Subscription]:
        """Return all subscriptions for a given strategy template."""
        collection = self._collection()
        cursor = collection.find({"strategy_code": strategy_code})
        return [Subscription.from_mongo(doc) async for doc in cursor]

    async def list_all(self) -> list[Subscription]:
        """Return every subscription in the collection — used for startup rehydration."""
        collection = self._collection()
        cursor = collection.find({})
        return [Subscription.from_mongo(doc) async for doc in cursor]

    async def update_desired_state(self, sub_id: str, state: RunState) -> int:
        """Set the control-plane desired_state. Returns modified_count (0 if no such sub)."""
        collection = self._collection()
        result = await collection.update_one({"_id": sub_id}, {"$set": {"desired_state": state}})
        logger.debug("subscription_desired_state_updated", sub_id=sub_id, state=state)
        return result.modified_count

    async def update_actual_state(self, sub_id: str, state: RunState) -> int:
        """Mirror observed RAM run-state into actual_state. Returns modified_count."""
        collection = self._collection()
        result = await collection.update_one({"_id": sub_id}, {"$set": {"actual_state": state}})
        logger.debug("subscription_actual_state_updated", sub_id=sub_id, state=state)
        return result.modified_count

    async def delete(self, sub_id: str) -> int:
        """Delete a subscription by ID. Returns deleted_count (0 or 1)."""
        collection = self._collection()
        result = await collection.delete_one({"_id": sub_id})
        logger.debug("subscription_deleted", sub_id=sub_id, count=result.deleted_count)
        return result.deleted_count

    async def delete_by_strategy_code(self, strategy_code: str) -> int:
        """Delete all subscriptions for a strategy template. Returns deleted_count."""
        collection = self._collection()
        result = await collection.delete_many({"strategy_code": strategy_code})
        logger.debug(
            "subscriptions_deleted_by_strategy_code",
            strategy_code=strategy_code,
            count=result.deleted_count,
        )
        return result.deleted_count

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index(
            "strategy_code",
            name="ix_subscriptions_strategy_code",
        )
        # Sole duplicate guard — ids are random uuid7, so without this index
        # two adds of the same triple would both land.
        await collection.create_index(
            [("strategy_code", 1), ("symbol", 1), ("interval", 1)],
            unique=True,
            name="ix_subscriptions_dedup_triple",
        )
        logger.info("subscription_indexes_created")
