"""Handler for getting backtest result."""

from pocketquant.backtest.domain import BacktestResult
from pocketquant.backtest.handlers.get_result.query import GetBacktestQuery
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles


@handles(GetBacktestQuery)
class GetBacktestHandler(Handler[GetBacktestQuery, BacktestResult | None]):
    """Handle GetBacktestQuery - retrieve backtest result by ID."""

    def __init__(self, backtest_repository: BacktestRepository):
        self._backtest_repo = backtest_repository

    async def handle(self, request: GetBacktestQuery) -> BacktestResult | None:
        """Fetch backtest result from repository."""
        return await self._backtest_repo.get(request.run_id)
