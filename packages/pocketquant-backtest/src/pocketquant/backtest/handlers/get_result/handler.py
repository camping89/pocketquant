from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.backtest.handlers.get_result.query import GetBacktestQuery
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles


@handles(GetBacktestQuery)
class GetBacktestHandler(Handler[GetBacktestQuery, BacktestResult | None]):
    def __init__(self, backtest_repository: BacktestRepository):
        self._backtest_repo = backtest_repository

    async def handle(self, request: GetBacktestQuery) -> BacktestResult | None:
        return await self._backtest_repo.get(request.run_id)
