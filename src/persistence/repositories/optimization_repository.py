"""Optimization repository for MongoDB persistence."""

from src.application.backtesting.models.optimization_result import OptimizationResult
from src.common.constants import COLLECTION_OPTIMIZATION_RUNS
from src.persistence.base_repository import BaseRepository


class OptimizationRepository(BaseRepository):
    """Repository for optimization run results."""

    _collection_name = COLLECTION_OPTIMIZATION_RUNS

    @staticmethod
    async def save(result: OptimizationResult) -> None:
        """Save or update optimization result."""
        collection = OptimizationRepository._collection()
        await collection.replace_one(
            {"_id": result.id}, result.to_dict(), upsert=True
        )

    @staticmethod
    async def get(optimization_id: str) -> OptimizationResult | None:
        """Get optimization result by ID."""
        collection = OptimizationRepository._collection()
        doc = await collection.find_one({"_id": optimization_id})

        if not doc:
            return None

        return OptimizationResult.from_dict(doc)

    @staticmethod
    async def ensure_indexes() -> None:
        """Create indexes for optimization queries."""
        collection = OptimizationRepository._collection()
        await collection.create_index("strategy_id")
        await collection.create_index("created_at")
