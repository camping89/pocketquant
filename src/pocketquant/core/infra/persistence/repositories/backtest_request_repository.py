from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from pocketquant.core.common.constants import COLLECTION_BACKTEST_REQUESTS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.core.infra.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


async def ensure_pending_sub_unique_index(collection: Any) -> None:
    """Create the pending-sub dedup index — single source for its spec.

    DB-level guarantee: at most one pending request per subscription. The
    $type guard keeps single-kind docs (sub_id=null) out of the index — two
    concurrent ad-hoc runs are legitimate. Called from both ensure_indexes and
    the boot migration so the spec can never drift between the two.
    """
    spec = {
        "unique": True,
        "partialFilterExpression": {"status": "pending", "sub_id": {"$type": "string"}},
        "name": "ix_backtest_requests_pending_sub",
    }
    try:
        await collection.create_index([("sub_id", 1)], **spec)
    except Exception as exc:
        # A same-name index with a different spec exists from an old deploy —
        # replace it. IndexOptionsConflict (85) / IndexKeySpecsConflict (86).
        if getattr(exc, "code", None) not in (85, 86):
            raise
        await collection.drop_index("ix_backtest_requests_pending_sub")
        await collection.create_index([("sub_id", 1)], **spec)


class BacktestRequestRepository(BaseRepository):
    """Mongo-backed work queue for backtest execution requests.

    The collection IS the queue. ``claim_next`` uses an atomic
    ``find_one_and_update`` (pending→running) so two app instances (VPS + local)
    never double-run the same request without any external lock layer.
    """

    _collection_name = COLLECTION_BACKTEST_REQUESTS

    async def enqueue(self, request: BacktestRequest) -> str:
        """Persist a pending request and return the persisted doc's id.

        Subscription requests dedup on (sub_id, status=pending): an upsert
        resets the sub's existing pending doc in place, so two concurrent
        run-all fan-outs collapse to a single pending doc per subscription
        instead of duplicating work. The partial unique index backs this at
        the DB level; the returned id is the PERSISTED doc's id, which may
        differ from ``request.id`` when an existing pending doc absorbed the
        enqueue. Terminal (done/failed) docs for the sub are dropped first so
        storage stays bounded at one generation per subscription.

        Single ad-hoc requests are independent work items — plain insert.
        """
        collection = self._collection()
        doc = request.to_mongo()

        if request.kind == "subscription" and request.sub_id is not None:
            return await self._enqueue_subscription(doc, sub_id=request.sub_id)

        await collection.insert_one(doc)
        logger.debug("backtest_request_enqueued", request_id=doc["_id"], kind=request.kind)
        return doc["_id"]

    async def _enqueue_subscription(self, doc: dict[str, Any], *, sub_id: str) -> str:
        """Dedup-enqueue one subscription request; returns the persisted id."""
        collection = self._collection()
        await collection.delete_many({"sub_id": sub_id, "status": {"$in": ["done", "failed"]}})

        candidate_id = doc.pop("_id")
        # Two enqueues racing through the upsert window can both take the
        # insert branch; the unique index rejects the loser. On retry the
        # loser's filter matches the winner's pending doc — both callers end
        # up referencing the single pending doc, which is the goal.
        for attempt in range(3):
            try:
                persisted = await collection.find_one_and_update(
                    {"sub_id": sub_id, "status": "pending"},
                    {"$set": doc, "$setOnInsert": {"_id": candidate_id}},
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
            except DuplicateKeyError:
                if attempt == 2:
                    raise
                continue
            if persisted is None:
                # Driver stubs allow None, but upsert + ReturnDocument.AFTER
                # always yields a doc — guard for type-safety only.
                raise RuntimeError("upsert returned no document")
            logger.debug(
                "backtest_request_enqueued", request_id=persisted["_id"], kind="subscription"
            )
            return persisted["_id"]
        raise RuntimeError("unreachable: enqueue retry loop exited without return/raise")

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

        Per-doc updates, not update_many: flipping a subscription doc back to
        pending moves it INTO the pending-sub unique index, and a newer pending
        doc for the same sub may legitimately exist (enqueued while the stale
        one was running). That collision means the newer request supersedes the
        stale one — mark the stale doc failed instead of pending, otherwise the
        raised DuplicateKeyError would abort the sweep on every tick.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=threshold_minutes)
        collection = self._collection()
        reclaimed = 0
        async for doc in collection.find({"status": "running", "started_at": {"$lt": cutoff}}):
            try:
                await collection.update_one(
                    {"_id": doc["_id"], "status": "running"},
                    {"$set": {"status": "pending"}, "$unset": {"started_at": ""}},
                )
            except DuplicateKeyError:
                await collection.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "status": "failed",
                            "finished_at": datetime.now(UTC),
                            "error": "stale running request superseded by a newer pending one",
                        }
                    },
                )
            reclaimed += 1
        if reclaimed:
            logger.info(
                "backtest_request_stale_reclaim",
                reclaimed=reclaimed,
                threshold_minutes=threshold_minutes,
            )
        return reclaimed

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index("status", name="ix_backtest_requests_status")
        await collection.create_index("requested_at", name="ix_backtest_requests_requested_at")
        await collection.create_index(
            [("status", 1), ("requested_at", 1)],
            name="ix_backtest_requests_status_requested",
        )
        await ensure_pending_sub_unique_index(collection)
        logger.info("backtest_request_indexes_created")
