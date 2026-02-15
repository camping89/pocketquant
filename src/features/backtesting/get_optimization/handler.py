"""Handler for getting optimization result."""

from src.application.backtesting.models.optimization_result import OptimizationResult
from src.common.mediator import Handler, handles
from src.features.backtesting.get_optimization.query import GetOptimizationQuery
from src.persistence.repositories.optimization_repository import OptimizationRepository


@handles(GetOptimizationQuery)
class GetOptimizationHandler(Handler[GetOptimizationQuery, OptimizationResult | None]):
    """Handle GetOptimizationQuery - retrieve optimization result by ID."""

    def __init__(self, optimization_repository: OptimizationRepository):
        self._optimization_repo = optimization_repository

    async def handle(self, request: GetOptimizationQuery) -> OptimizationResult | None:
        """Fetch optimization result from MongoDB."""
        return await self._optimization_repo.get(request.optimization_id)
