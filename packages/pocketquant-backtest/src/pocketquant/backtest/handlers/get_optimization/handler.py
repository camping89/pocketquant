"""Handler for getting optimization result."""

from pocketquant.backtest.domain import OptimizationResult
from pocketquant.backtest.handlers.get_optimization.query import GetOptimizationQuery
from pocketquant.backtest.persistence.optimization_repository import OptimizationRepository
from pocketquant.core.common.mediator import Handler, handles


@handles(GetOptimizationQuery)
class GetOptimizationHandler(Handler[GetOptimizationQuery, OptimizationResult | None]):
    """Handle GetOptimizationQuery - retrieve optimization result by ID."""

    def __init__(self, optimization_repository: OptimizationRepository):
        self._optimization_repo = optimization_repository

    async def handle(self, request: GetOptimizationQuery) -> OptimizationResult | None:
        """Fetch optimization result from MongoDB."""
        return await self._optimization_repo.get(request.optimization_id)
