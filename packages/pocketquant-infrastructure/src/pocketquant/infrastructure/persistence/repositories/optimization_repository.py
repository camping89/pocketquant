"""Optimization repository for MongoDB persistence."""

from pocketquant.core.common.constants import COLLECTION_BACKTEST_OPTIMIZATION_RUNS
from pocketquant.core.domain.backtest import OptimizationResult
from pocketquant.infrastructure.persistence.base_repository import BaseRepository


class OptimizationRepository(BaseRepository):
    _collection_name = COLLECTION_BACKTEST_OPTIMIZATION_RUNS

    async def save(self, result: OptimizationResult) -> None:
        collection = self._collection()
        await collection.replace_one({"_id": result.id}, result.to_mongo(), upsert=True)

    async def get(self, optimization_id: str) -> OptimizationResult | None:
        collection = self._collection()
        doc = await collection.find_one({"_id": optimization_id})

        if not doc:
            return None

        return OptimizationResult.from_mongo(doc)

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index("strategy_code", name="ix_optimizations_strategy_code")
        await collection.create_index("created_at", name="ix_optimizations_created_at")
