"""Handler for getting optimization result."""

from src.common.constants import COLLECTION_OPTIMIZATION_RUNS
from src.common.database import Database
from src.common.mediator import Handler, handles
from src.features.backtesting.base.models.optimization_result import OptimizationResult
from src.features.backtesting.get_optimization.query import GetOptimizationQuery


@handles(GetOptimizationQuery)
class GetOptimizationHandler(Handler[GetOptimizationQuery, OptimizationResult | None]):
    """Handle GetOptimizationQuery - retrieve optimization result by ID."""

    async def handle(self, request: GetOptimizationQuery) -> OptimizationResult | None:
        """Fetch optimization result from MongoDB."""
        collection = Database.get_collection(COLLECTION_OPTIMIZATION_RUNS)
        doc = await collection.find_one({"_id": request.optimization_id})

        if not doc:
            return None

        return OptimizationResult.from_dict(doc)
