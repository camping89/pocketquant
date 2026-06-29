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
        collection = self._collection()
        doc = result.to_mongo()
        await collection.replace_one({"_id": str(result.id)}, doc, upsert=True)
        logger.debug(
            "backtest_result_saved", run_id=str(result.id), strategy_code=result.strategy_code
        )
        return str(result.id)

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
            query["status"] = "finished"

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
            collection.find({"strategy_code": strategy_code, "status": "finished"})
            .sort(f"metrics.{metric}", -1)
            .limit(limit)
        )

        results = []
        async for doc in cursor:
            results.append(BacktestResult.from_mongo(doc))
        return results

    async def mark_failed(self, run_id: str, error_message: str) -> None:
        """Flip a run to ``failed`` with an error — used when the spawn path or a
        non-engine error aborts before the engine persisted its own result doc."""
        collection = self._collection()
        await collection.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": error_message,
                    "completed_at": datetime.now(UTC),
                }
            },
        )
        logger.debug("backtest_marked_failed", run_id=run_id)

    async def set_verdict(self, run_id: str, verdict: str | None) -> bool:
        """Set the human-readable verdict on a run without touching metrics.

        Returns False if no run matches ``run_id`` so the caller can 404.
        """
        collection = self._collection()
        result = await collection.update_one(
            {"_id": run_id}, {"$set": {"verdict": verdict}}
        )
        return result.matched_count > 0

    async def mark_orphaned_started_as_failed(self) -> int:
        """Flip every run still ``started`` to ``failed`` — call once at boot.

        The app is a single uvicorn worker, so no legitimately in-flight run can
        survive a restart: any ``started`` doc is a task killed mid-run. Without
        this, the doc stays ``started`` forever and FE polls it indefinitely.
        Returns the count updated.
        """
        collection = self._collection()
        result = await collection.update_many(
            {"status": "started"},
            {"$set": {"status": "failed", "error_message": "interrupted_by_restart"}},
        )
        if result.modified_count:
            logger.info("backtest_orphan_recovery", marked_failed=result.modified_count)
        return result.modified_count

    async def delete(self, run_id: str) -> bool:
        collection = self._collection()
        result = await collection.delete_one({"_id": run_id})
        return result.deleted_count > 0

    async def delete_by_strategy_code(self, strategy_code: str) -> int:
        collection = self._collection()
        result = await collection.delete_many({"strategy_code": strategy_code})
        logger.debug(
            "backtests_deleted_by_strategy_code",
            strategy_code=strategy_code,
            count=result.deleted_count,
        )
        return result.deleted_count

    async def ensure_indexes(self) -> None:
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
        logger.info("backtest_indexes_created")
