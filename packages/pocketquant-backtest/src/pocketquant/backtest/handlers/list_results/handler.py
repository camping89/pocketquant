"""Handler for listing backtests."""

from pocketquant.backtest.domain import BacktestResult
from pocketquant.backtest.handlers.list_results.query import ListBacktestsQuery
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles


@handles(ListBacktestsQuery)
class ListBacktestsHandler(Handler[ListBacktestsQuery, list[BacktestResult]]):
    """Handle ListBacktestsQuery - list backtest results for a strategy."""

    def __init__(self, backtest_repository: BacktestRepository):
        self._backtest_repo = backtest_repository

    async def handle(self, request: ListBacktestsQuery) -> list[BacktestResult]:
        """Fetch backtest results from repository."""
        return await self._backtest_repo.list_by_strategy(
            strategy_id=request.strategy_id,
            limit=request.limit,
            include_failed=request.include_failed,
        )
