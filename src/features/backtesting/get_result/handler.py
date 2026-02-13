"""Handler for getting backtest result."""

from src.common.mediator import Handler
from src.features.backtesting.base.models.backtest_result import BacktestResult
from src.features.backtesting.base.repository.backtest_repository import BacktestRepository
from src.features.backtesting.get_result.query import GetBacktestQuery


class GetBacktestHandler(Handler[GetBacktestQuery, BacktestResult | None]):
    """Handle GetBacktestQuery - retrieve backtest result by ID."""

    async def handle(self, request: GetBacktestQuery) -> BacktestResult | None:
        """Fetch backtest result from repository."""
        return await BacktestRepository.get(request.run_id)
