"""Optimization repository for MongoDB persistence."""

from pocketquant.backtest.domain import OptimizationResult
from pocketquant.core.common.constants import COLLECTION_OPTIMIZATION_RUNS
from pocketquant.core.persistence.base_repository import BaseRepository


class OptimizationRepository(BaseRepository):
    """Repository for optimization run results."""

    _collection_name = COLLECTION_OPTIMIZATION_RUNS

    async def save(self, result: OptimizationResult) -> None:
        """Save or update optimization result."""
        collection = self._collection()
        await collection.replace_one({"_id": result.id}, result.to_mongo(), upsert=True)

    async def get(self, optimization_id: str) -> OptimizationResult | None:
        """Get optimization result by ID."""
        collection = self._collection()
        doc = await collection.find_one({"_id": optimization_id})

        if not doc:
            return None

        return OptimizationResult.from_mongo(doc)

    async def ensure_indexes(self) -> None:
        """Create indexes for optimization queries."""
        collection = self._collection()
        await collection.create_index("strategy_id", name="ix_optimizations_strategy_id")
        await collection.create_index("created_at", name="ix_optimizations_created_at")
