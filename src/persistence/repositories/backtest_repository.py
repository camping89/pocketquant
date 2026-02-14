"""Backtest repository - MongoDB persistence for backtest runs and results."""

from typing import Any

from src.application.backtesting.models.backtest_result import BacktestResult
from src.common.constants import COLLECTION_BACKTEST_RUNS
from src.common.logging import get_logger
from src.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class BacktestRepository(BaseRepository):
    """MongoDB repository for backtest run persistence.

    Collections:
    - backtest_runs: Stores BacktestResult documents with metrics and equity curves.

    Indexes:
    - strategy_id: For querying runs by strategy
    - started_at: For time-based queries
    - status: For filtering by completion status
    """

    _collection_name = COLLECTION_BACKTEST_RUNS

    @staticmethod
    async def save(result: BacktestResult) -> str:
        """Save or update a backtest result.

        Args:
            result: The BacktestResult to persist.

        Returns:
            The result ID.
        """
        collection = BacktestRepository._collection()
        doc = result.to_dict()

        await collection.replace_one({"_id": result.id}, doc, upsert=True)

        logger.debug("backtest_result_saved", run_id=result.id, strategy_id=result.strategy_id)
        return result.id

    @staticmethod
    async def get(run_id: str) -> BacktestResult | None:
        """Get a backtest result by ID.

        Args:
            run_id: The unique run identifier.

        Returns:
            BacktestResult if found, None otherwise.
        """
        collection = BacktestRepository._collection()
        doc = await collection.find_one({"_id": run_id})

        if not doc:
            return None

        return BacktestResult.from_dict(doc)

    @staticmethod
    async def list_by_strategy(
        strategy_id: str, limit: int = 20, include_failed: bool = False
    ) -> list[BacktestResult]:
        """List recent backtest runs for a strategy.

        Args:
            strategy_id: Strategy identifier to filter by.
            limit: Maximum number of results (default 20).
            include_failed: Include failed runs in results (default False).

        Returns:
            List of BacktestResult ordered by started_at descending.
        """
        collection = BacktestRepository._collection()

        query: dict[str, Any] = {"strategy_id": strategy_id}
        if not include_failed:
            query["status"] = "completed"

        cursor = collection.find(query).sort("started_at", -1).limit(limit)

        results = []
        async for doc in cursor:
            results.append(BacktestResult.from_dict(doc))

        return results

    @staticmethod
    async def get_best_by_metric(
        strategy_id: str, metric: str = "sharpe_ratio", limit: int = 10
    ) -> list[BacktestResult]:
        """Get top backtest results ranked by a specific metric.

        Args:
            strategy_id: Strategy identifier to filter by.
            metric: Metric name to sort by (must be in metrics subdocument).
            limit: Maximum number of results.

        Returns:
            List of BacktestResult ordered by metric descending.
        """
        collection = BacktestRepository._collection()

        cursor = (
            collection.find({"strategy_id": strategy_id, "status": "completed"})
            .sort(f"metrics.{metric}", -1)
            .limit(limit)
        )

        results = []
        async for doc in cursor:
            results.append(BacktestResult.from_dict(doc))

        return results

    @staticmethod
    async def delete(run_id: str) -> bool:
        """Delete a backtest result.

        Args:
            run_id: The unique run identifier.

        Returns:
            True if deleted, False if not found.
        """
        collection = BacktestRepository._collection()
        result = await collection.delete_one({"_id": run_id})
        return result.deleted_count > 0

    @staticmethod
    async def ensure_indexes() -> None:
        """Create indexes for efficient queries."""
        collection = BacktestRepository._collection()

        await collection.create_index("strategy_id")
        await collection.create_index("started_at")
        await collection.create_index("status")
        await collection.create_index([("strategy_id", 1), ("started_at", -1)])
        await collection.create_index([("strategy_id", 1), ("metrics.sharpe_ratio", -1)])

        logger.info("backtest_indexes_created")
