from pocketquant.backtest.handlers.get_result.query import GetBacktestQuery
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.persistence.repositories.backtest_repository import (
    BacktestRepository,
)


@handles(GetBacktestQuery)
class GetBacktestHandler(Handler[GetBacktestQuery, BacktestResult | None]):
    def __init__(self, backtest_repository: BacktestRepository):
        self._backtest_repo = backtest_repository

    async def handle(self, request: GetBacktestQuery) -> BacktestResult | None:
        return await self._backtest_repo.get(request.run_id)
