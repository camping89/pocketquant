from datetime import UTC, datetime, timedelta
from typing import Any

from pocketquant.core.common.constants import COLLECTION_BACKTEST_REQUESTS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.infrastructure.persistence.base_repository import BaseRepository
from pymongo import ReturnDocument

logger = get_logger(__name__)


class BacktestRequestRepository(BaseRepository):
    """Mongo-backed work queue for backtest execution requests.

    The collection IS the queue. ``claim_next`` uses an atomic
    ``find_one_and_update`` (pending→running) so two app instances (VPS + local)
    never double-run the same request without any external lock layer.
    """

    _collection_name = COLLECTION_BACKTEST_REQUESTS

    async def enqueue(self, request: BacktestRequest) -> str:
        """Upsert a request by id, resetting it to its enqueued (pending) state.

        Upsert (not insert) makes re-enqueue idempotent: subscription requests
        carry a deterministic id keyed on the subscription, so two concurrent
        run-all fan-outs collapse to a single pending doc per subscription
        instead of duplicating work. Single ad-hoc requests use unique ids, so
        the upsert is an insert for them.
        """
        collection = self._collection()
        await collection.replace_one({"_id": request.id}, request.to_mongo(), upsert=True)
        logger.debug("backtest_request_enqueued", request_id=request.id, kind=request.kind)
        return request.id

    async def claim_next(self) -> BacktestRequest | None:
        """Atomically flip the oldest pending request to running and return it.

        Returns None when the queue holds no pending request. The atomic
        find-one-and-update is the only synchronization needed — concurrent
        workers cannot claim the same doc.
        """
        collection = self._collection()
        doc = await collection.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "running", "started_at": datetime.now(UTC)}},
            sort=[("requested_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return None
        return BacktestRequest.from_mongo(doc)

    async def get(self, request_id: str) -> BacktestRequest | None:
        collection = self._collection()
        doc = await collection.find_one({"_id": request_id})
        if doc is None:
            return None
        return BacktestRequest.from_mongo(doc)

    async def mark_done(self, request_id: str, result: dict[str, Any] | None = None) -> None:
        collection = self._collection()
        await collection.update_one(
            {"_id": request_id},
            {"$set": {"status": "done", "finished_at": datetime.now(UTC), "result": result}},
        )
        logger.debug("backtest_request_done", request_id=request_id)

    async def mark_failed(self, request_id: str, error: str) -> None:
        collection = self._collection()
        await collection.update_one(
            {"_id": request_id},
            {
                "$set": {
                    "status": "failed",
                    "finished_at": datetime.now(UTC),
                    "error": error[:500],
                }
            },
        )
        logger.debug("backtest_request_failed", request_id=request_id)

    async def delete_by_subscription(self, sub_id: str) -> int:
        """Delete queued requests for one subscription. Returns deleted_count.

        Keeps the queue from holding orphan work after a subscription is removed.
        """
        collection = self._collection()
        result = await collection.delete_many({"sub_id": sub_id})
        return result.deleted_count

    async def delete_by_strategy_code(self, strategy_code: str) -> int:
        """Delete queued requests for a strategy template. Returns deleted_count."""
        collection = self._collection()
        result = await collection.delete_many({"strategy_code": strategy_code})
        return result.deleted_count

    async def reclaim_stale_running(self, threshold_minutes: int = 10) -> int:
        """Reset requests stuck in 'running' beyond threshold back to 'pending'.

        Guards against a worker that claimed a request then died before writing
        terminal status — the request would otherwise wait forever. Idempotent;
        returns the count reset. Uses ``started_at`` set by ``claim_next``.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=threshold_minutes)
        collection = self._collection()
        result = await collection.update_many(
            {"status": "running", "started_at": {"$lt": cutoff}},
            {"$set": {"status": "pending"}, "$unset": {"started_at": ""}},
        )
        if result.modified_count:
            logger.info(
                "backtest_request_stale_reclaim",
                reclaimed=result.modified_count,
                threshold_minutes=threshold_minutes,
            )
        return result.modified_count

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index("status", name="ix_backtest_requests_status")
        await collection.create_index("requested_at", name="ix_backtest_requests_requested_at")
        await collection.create_index(
            [("status", 1), ("requested_at", 1)],
            name="ix_backtest_requests_status_requested",
        )
        logger.info("backtest_request_indexes_created")
