"""Handler for listing backtests."""

from src.common.mediator import Handler, handles
from src.features.backtesting.base.models.backtest_result import BacktestResult
from src.features.backtesting.base.repository.backtest_repository import BacktestRepository
from src.features.backtesting.list_results.query import ListBacktestsQuery


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
