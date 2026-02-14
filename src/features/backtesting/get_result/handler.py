"""Handler for getting backtest result."""

from src.application.backtesting.models.backtest_result import BacktestResult
from src.common.mediator import Handler, handles
from src.features.backtesting.get_result.query import GetBacktestQuery
from src.infrastructure.persistence.repositories.backtest_repository import BacktestRepository


@handles(GetBacktestQuery)
class GetBacktestHandler(Handler[GetBacktestQuery, BacktestResult | None]):
    """Handle GetBacktestQuery - retrieve backtest result by ID."""

    async def handle(self, request: GetBacktestQuery) -> BacktestResult | None:
        """Fetch backtest result from repository."""
        return await BacktestRepository.get(request.run_id)
