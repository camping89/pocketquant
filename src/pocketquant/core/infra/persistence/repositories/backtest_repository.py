from datetime import UTC, datetime
from typing import Any

from pocketquant.core.common.constants import COLLECTION_BACKTEST_RUNS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.infra.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class BacktestRepository(BaseRepository):
    _collection_name = COLLECTION_BACKTEST_RUNS

    async def save(self, result: BacktestResult) -> str:
        """Save or update a backtest result. Returns the result ID."""
        collection = self._collection()
        doc = result.to_mongo()
        await collection.replace_one({"_id": result.id}, doc, upsert=True)
        logger.debug("backtest_result_saved", run_id=result.id, strategy_code=result.strategy_code)
        return result.id

    async def get(self, run_id: str) -> BacktestResult | None:
        collection = self._collection()
        doc = await collection.find_one({"_id": run_id})
        if not doc:
            return None
        return BacktestResult.from_mongo(doc)

    async def list_by_strategy_code(
        self, strategy_code: str, limit: int = 20, include_failed: bool = False
    ) -> list[BacktestResult]:
        collection = self._collection()

        query: dict[str, Any] = {"strategy_code": strategy_code}
        if not include_failed:
            query["status"] = "completed"

        cursor = collection.find(query).sort("started_at", -1).limit(limit)

        results = []
        async for doc in cursor:
            results.append(BacktestResult.from_mongo(doc))
        return results

    async def get_best_by_metric(
        self, strategy_code: str, metric: str = "sharpe_ratio", limit: int = 10
    ) -> list[BacktestResult]:
        collection = self._collection()

        cursor = (
            collection.find({"strategy_code": strategy_code, "status": "completed"})
            .sort(f"metrics.{metric}", -1)
            .limit(limit)
        )

        results = []
        async for doc in cursor:
            results.append(BacktestResult.from_mongo(doc))
        return results

    async def delete(self, run_id: str) -> bool:
        """Delete a backtest result. Returns True if deleted."""
        collection = self._collection()
        result = await collection.delete_one({"_id": run_id})
        return result.deleted_count > 0

    # ------------------------------------------------------------------
    # Subscription-scoped methods (one cached result per subscription)
    # ------------------------------------------------------------------

    async def find_by_subscription(self, sub_id: str) -> BacktestResult | None:
        """Return the cached backtest result for a subscription, or None."""
        collection = self._collection()
        doc = await collection.find_one({"_id": sub_id})
        if not doc:
            return None
        return BacktestResult.from_mongo(doc)

    async def upsert_status(
        self,
        sub_id: str,
        *,
        strategy_code: str,
        status: str,
        error_msg: str | None = None,
    ) -> None:
        """Upsert a lightweight status document for a subscription.

        Used by the worker to mark a run as 'running' or 'failed' without
        persisting a full BacktestResult. The _id equals sub_id so there is
        exactly one doc per subscription in this collection.
        """
        collection = self._collection()
        now = datetime.now(UTC)
        await collection.update_one(
            {"_id": sub_id},
            {
                "$set": {
                    "subscription_id": sub_id,
                    "strategy_code": strategy_code,
                    "status": status,
                    "last_run_at": now,
                    "error_msg": error_msg,
                },
                "$setOnInsert": {"_id": sub_id},
            },
            upsert=True,
        )
        logger.debug("backtest_status_upserted", sub_id=sub_id, status=status)

    async def save_for_subscription(self, sub_id: str, result: BacktestResult) -> None:
        """Upsert a full BacktestResult keyed by subscription ID.

        Overwrites any previous result for this subscription. The document _id
        equals sub_id so cache lookups are O(1) primary-key reads.

        Status mapping (subscription vocabulary):
          result.status == 'completed' → stored as 'completed'
          result.status == 'failed'    → stored as 'failed', error_msg copied
          anything else                → stored as 'completed' (safe fallback)
        """
        collection = self._collection()
        # BacktestResult is a mutable dataclass; override id so to_mongo() _id is consistent
        result.id = sub_id
        doc = result.to_mongo()
        doc["_id"] = sub_id  # ensure _id matches regardless of result.id
        doc["subscription_id"] = sub_id
        doc["last_run_at"] = datetime.now(UTC)

        # Map engine status to subscription vocabulary
        if result.status == "failed":
            doc["status"] = "failed"
            doc["error_msg"] = result.error_message or "backtest_engine_error"
        else:
            # 'completed' or any other value → mark successful
            doc["status"] = "completed"
            doc["error_msg"] = None

        await collection.replace_one({"_id": sub_id}, doc, upsert=True)
        logger.debug("backtest_saved_for_subscription", sub_id=sub_id, status=doc["status"])

    async def delete_by_subscription(self, sub_id: str) -> int:
        """Delete the cached result for a single subscription. Returns deleted_count."""
        collection = self._collection()
        result = await collection.delete_one({"_id": sub_id})
        logger.debug("backtest_deleted_by_subscription", sub_id=sub_id, count=result.deleted_count)
        return result.deleted_count

    async def delete_by_strategy_code(self, strategy_code: str) -> int:
        """Delete all backtest docs for a strategy template. Returns deleted_count."""
        collection = self._collection()
        result = await collection.delete_many({"strategy_code": strategy_code})
        logger.debug(
            "backtests_deleted_by_strategy_code",
            strategy_code=strategy_code,
            count=result.deleted_count,
        )
        return result.deleted_count

    async def get_subscription_status(self, sub_id: str) -> dict | None:
        """Return lightweight status doc {status, last_run_at, error_msg} or None.

        Used by ListSymbolsHandler to enrich subscription list without deserialising
        a full BacktestResult (which may fail for status-only docs like 'running').
        """
        collection = self._collection()
        doc = await collection.find_one(
            {"_id": sub_id},
            projection={"status": 1, "last_run_at": 1, "error_msg": 1},
        )
        if doc is None:
            return None
        return {
            "status": doc.get("status"),
            "last_run_at": doc["last_run_at"].isoformat() if doc.get("last_run_at") else None,
            "error_msg": doc.get("error_msg"),
        }

    async def get_subscription_statuses(self, sub_ids: list[str]) -> dict[str, dict]:
        """Return {sub_id: {status, last_run_at, error_msg}} for given sub_ids.

        Single batched query — use instead of calling get_subscription_status() in a loop.
        """
        if not sub_ids:
            return {}
        collection = self._collection()
        cursor = collection.find(
            {"_id": {"$in": sub_ids}, "subscription_id": {"$exists": True}},
            projection={
                "subscription_id": 1,
                "status": 1,
                "last_run_at": 1,
                "error_msg": 1,
                "_id": 1,
            },
        )
        out: dict[str, dict] = {}
        async for doc in cursor:
            out[doc["_id"]] = {
                "status": doc.get("status"),
                "last_run_at": doc["last_run_at"].isoformat() if doc.get("last_run_at") else None,
                "error_msg": doc.get("error_msg"),
            }
        return out

    async def find_doc_by_subscription(self, sub_id: str) -> dict | None:
        """Return the raw MongoDB document for a subscription's backtest.

        Safer than find_by_subscription() for status-only docs ('running'/'failed')
        that lack the full BacktestResult fields needed by BacktestResult.from_mongo().
        Replaces '_id' key with 'id' for clean client responses.
        """
        collection = self._collection()
        doc = await collection.find_one({"_id": sub_id})
        if doc is None:
            return None
        doc["id"] = doc.pop("_id")
        # Normalise datetime fields to ISO strings for JSON serialisation
        for field in ("last_run_at", "started_at", "completed_at"):
            if field in doc and hasattr(doc[field], "isoformat"):
                doc[field] = doc[field].isoformat()
        return doc

    async def mark_stale_running_as_failed(self, threshold_minutes: int = 10) -> int:
        """Mark backtest docs stuck in 'running' beyond threshold_minutes as 'failed'.

        Idempotent — safe to call repeatedly. Uses last_run_at set by upsert_status().
        Returns the count of documents updated.
        """
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(minutes=threshold_minutes)
        collection = self._collection()
        result = await collection.update_many(
            {"status": "running", "last_run_at": {"$lt": cutoff}},
            {"$set": {"status": "failed", "error_msg": "stale_recovery"}},
        )
        if result.modified_count:
            logger.info(
                "backtest_stale_recovery",
                marked_failed=result.modified_count,
                threshold_minutes=threshold_minutes,
            )
        return result.modified_count

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient queries."""
        collection = self._collection()
        await collection.create_index("strategy_code", name="ix_backtests_strategy_code")
        await collection.create_index("started_at", name="ix_backtests_started_at")
        await collection.create_index("status", name="ix_backtests_status")
        await collection.create_index(
            [("strategy_code", 1), ("started_at", -1)],
            name="ix_backtests_strategy_code_started",
        )
        await collection.create_index(
            [("strategy_code", 1), ("metrics.sharpe_ratio", -1)],
            name="ix_backtests_strategy_code_sharpe",
        )
        await collection.create_index(
            [("strategy_code", 1), ("metrics.sortino_ratio", -1)],
            name="ix_backtests_strategy_code_sortino",
        )
        await collection.create_index(
            [("strategy_code", 1), ("metrics.win_rate", -1)],
            name="ix_backtests_strategy_code_winrate",
        )
        # Sparse unique index so legacy docs without subscription_id are unaffected
        await collection.create_index(
            "subscription_id",
            name="ix_backtests_subscription_id_unique",
            unique=True,
            sparse=True,
        )
        logger.info("backtest_indexes_created")
