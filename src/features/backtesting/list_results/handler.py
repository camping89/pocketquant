"""Handler for listing backtests."""

from src.application.backtesting.models.backtest_result import BacktestResult
from src.common.mediator import Handler, handles
from src.features.backtesting.list_results.query import ListBacktestsQuery
from src.infrastructure.persistence.repositories.backtest_repository import BacktestRepository


@handles(ListBacktestsQuery)
class ListBacktestsHandler(Handler[ListBacktestsQuery, list[BacktestResult]]):
    """Handle ListBacktestsQuery - list backtest results for a strategy."""

    async def handle(self, request: ListBacktestsQuery) -> list[BacktestResult]:
        """Fetch backtest results from repository."""
        return await BacktestRepository.list_by_strategy(
            strategy_id=request.strategy_id,
            limit=request.limit,
            include_failed=request.include_failed,
        )
