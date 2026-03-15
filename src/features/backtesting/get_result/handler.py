"""Handler for getting backtest result."""

from src.domain.backtest import BacktestResult
from src.common.mediator import Handler, handles
from src.features.backtesting.get_result.query import GetBacktestQuery
from src.persistence.repositories.backtest_repository import BacktestRepository


@handles(GetBacktestQuery)
class GetBacktestHandler(Handler[GetBacktestQuery, BacktestResult | None]):
    """Handle GetBacktestQuery - retrieve backtest result by ID."""

    def __init__(self, backtest_repository: BacktestRepository):
        self._backtest_repo = backtest_repository

    async def handle(self, request: GetBacktestQuery) -> BacktestResult | None:
        """Fetch backtest result from repository."""
        return await self._backtest_repo.get(request.run_id)
