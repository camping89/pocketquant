from pymongo.errors import DuplicateKeyError

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import utc_now
from pocketquant.core.domain.subscription import (
    ManualAction,
    RunState,
    Subscription,
    SubscriptionAlreadyExistsError,
)
from pocketquant.core.infra.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class SubscriptionRepository(BaseRepository):
    _collection_name = "subscriptions"

    # DuplicateKeyError comes from the unique intervals-key index: two adds of one interval
    # set carry different uuid7 ids yet still collide.
    async def add(self, sub: Subscription) -> None:
        doc = sub.to_mongo()
        try:
            await self._collection().insert_one(doc)
            logger.debug("subscription_added", sub_id=str(sub.id), strategy_code=sub.strategy_code)
        except DuplicateKeyError:
            raise SubscriptionAlreadyExistsError(
                sub.strategy_code, sub.symbol, doc["intervals_key"]
            ) from None

    # The filter refuses a running subscription, so the caller's stopped check cannot race
    # a start; the return is matched_count, as in update_desired_state.
    async def update_config(self, sub: Subscription) -> int:
        doc = sub.to_mongo()
        try:
            result = await self._collection().update_one(
                {"_id": str(sub.id), "desired_state": "stopped", "actual_state": "stopped"},
                {
                    "$set": {
                        "intervals": doc["intervals"],
                        "intervals_key": doc["intervals_key"],
                        "parameters": doc["parameters"],
                    }
                },
            )
        except DuplicateKeyError:
            raise SubscriptionAlreadyExistsError(
                sub.strategy_code, sub.symbol, doc["intervals_key"]
            ) from None
        logger.debug("subscription_config_updated", sub_id=str(sub.id))
        return result.matched_count

    async def get(self, sub_id: str) -> Subscription | None:
        collection = self._collection()
        doc = await collection.find_one({"_id": sub_id})
        if not doc:
            return None
        return Subscription.from_mongo(doc)

    async def list_by_strategy_code(self, strategy_code: str) -> list[Subscription]:
        collection = self._collection()
        cursor = collection.find({"strategy_code": strategy_code})
        return [Subscription.from_mongo(doc) async for doc in cursor]

    async def list_by_symbol(self, symbol: str) -> list[Subscription]:
        cursor = self._collection().find({"symbol": symbol})
        return [Subscription.from_mongo(doc) async for doc in cursor]

    async def list_all(self) -> list[Subscription]:
        collection = self._collection()
        cursor = collection.find({})
        return [Subscription.from_mongo(doc) async for doc in cursor]

    async def update_desired_state(self, sub_id: str, state: RunState) -> int:
        # matched_count, not modified_count: re-setting the same state is a no-op
        # write (modified_count == 0) yet the sub exists — callers use the return
        # value as an existence check, so it must count matches, not value changes.
        collection = self._collection()
        result = await collection.update_one({"_id": sub_id}, {"$set": {"desired_state": state}})
        logger.debug("subscription_desired_state_updated", sub_id=sub_id, state=state)
        return result.matched_count

    async def update_actual_state(self, sub_id: str, state: RunState) -> int:
        collection = self._collection()
        result = await collection.update_one({"_id": sub_id}, {"$set": {"actual_state": state}})
        logger.debug("subscription_actual_state_updated", sub_id=sub_id, state=state)
        return result.matched_count

    # A missing field matches None, so documents written before the field existed need no
    # migration.
    async def request_action(self, sub_id: str, action: ManualAction) -> int:
        result = await self._collection().update_one(
            {"_id": sub_id, "manual_action": None}, {"$set": {"manual_action": action}}
        )
        return result.modified_count

    # The filter on the attempted action leaves a different, newer request in place.
    async def clear_action(self, sub_id: str, action: ManualAction, outcome: str) -> int:
        result = await self._collection().update_one(
            {"_id": sub_id, "manual_action": action},
            {
                "$set": {
                    "manual_action": None,
                    "manual_action_outcome": {
                        "action": action,
                        "outcome": outcome,
                        "at": utc_now(),
                    },
                }
            },
        )
        return result.modified_count

    async def delete(self, sub_id: str) -> int:
        collection = self._collection()
        result = await collection.delete_one({"_id": sub_id})
        logger.debug("subscription_deleted", sub_id=sub_id, count=result.deleted_count)
        return result.deleted_count

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index(
            "strategy_code",
            name="ix_subscriptions_strategy_code",
        )
        # Sole duplicate guard — ids are random uuid7, so without this index two adds of
        # one interval set would both land. The key is a scalar because a unique index on
        # the list would be multikey and reject two lists that share one interval.
        await collection.create_index(
            [("strategy_code", 1), ("symbol", 1), ("intervals_key", 1)],
            unique=True,
            name="ix_subscriptions_dedup_intervals",
        )
        logger.info("subscription_indexes_created")
