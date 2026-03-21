"""Backtest repository - MongoDB persistence for backtest runs and results."""

from typing import Any

from pocketquant.backtest.domain import BacktestResult
from pocketquant.core.common.constants import COLLECTION_BACKTEST_RUNS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class BacktestRepository(BaseRepository):
    """MongoDB repository for backtest run persistence."""

    _collection_name = COLLECTION_BACKTEST_RUNS

    async def save(self, result: BacktestResult) -> str:
        """Save or update a backtest result. Returns the result ID."""
        collection = self._collection()
        doc = result.to_mongo()
        await collection.replace_one({"_id": result.id}, doc, upsert=True)
        logger.debug("backtest_result_saved", run_id=result.id, strategy_id=result.strategy_id)
        return result.id

    async def get(self, run_id: str) -> BacktestResult | None:
        """Get a backtest result by ID."""
        collection = self._collection()
        doc = await collection.find_one({"_id": run_id})
        if not doc:
            return None
        return BacktestResult.from_mongo(doc)

    async def list_by_strategy(
        self, strategy_id: str, limit: int = 20, include_failed: bool = False
    ) -> list[BacktestResult]:
        """List recent backtest runs for a strategy."""
        collection = self._collection()

        query: dict[str, Any] = {"strategy_id": strategy_id}
        if not include_failed:
            query["status"] = "completed"

        cursor = collection.find(query).sort("started_at", -1).limit(limit)

        results = []
        async for doc in cursor:
            results.append(BacktestResult.from_mongo(doc))
        return results

    async def get_best_by_metric(
        self, strategy_id: str, metric: str = "sharpe_ratio", limit: int = 10
    ) -> list[BacktestResult]:
        """Get top backtest results ranked by a specific metric."""
        collection = self._collection()

        cursor = (
            collection.find({"strategy_id": strategy_id, "status": "completed"})
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

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient queries."""
        collection = self._collection()
        await collection.create_index("strategy_id", name="ix_backtests_strategy_id")
        await collection.create_index("started_at", name="ix_backtests_started_at")
        await collection.create_index("status", name="ix_backtests_status")
        await collection.create_index(
            [("strategy_id", 1), ("started_at", -1)],
            name="ix_backtests_strategy_started",
        )
        await collection.create_index(
            [("strategy_id", 1), ("metrics.sharpe_ratio", -1)],
            name="ix_backtests_strategy_sharpe",
        )
        await collection.create_index(
            [("strategy_id", 1), ("metrics.sortino_ratio", -1)],
            name="ix_backtests_strategy_sortino",
        )
        await collection.create_index(
            [("strategy_id", 1), ("metrics.win_rate", -1)],
            name="ix_backtests_strategy_winrate",
        )
        logger.info("backtest_indexes_created")
