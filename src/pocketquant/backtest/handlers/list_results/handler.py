from pocketquant.backtest.handlers.list_results.query import ListBacktestsQuery
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.persistence.repositories.backtest_repository import (
    BacktestRepository,
)


@handles(ListBacktestsQuery)
class ListBacktestsHandler(Handler[ListBacktestsQuery, list[BacktestResult]]):
    def __init__(self, backtest_repository: BacktestRepository):
        self._backtest_repo = backtest_repository

    async def handle(self, request: ListBacktestsQuery) -> list[BacktestResult]:
        return await self._backtest_repo.list_by_strategy_code(
            strategy_code=request.strategy_id,
            limit=request.limit,
            include_failed=request.include_failed,
        )
