"""Backtest provider — shared dispatch deps + single-run execution service.

The ``/backtest/run`` route allocates a run id, persists the started doc, then
spawns ``BacktestExecutionService.execute_and_persist`` as an asyncio task.
"""

from dishka import Provider, Scope, provide

from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.backtest.backtest_dispatch import BacktestDispatchDeps
from pocketquant.engine.backtest.backtest_execution_service import BacktestExecutionService


class BacktestWorkerProvider(Provider):
    @provide(scope=Scope.APP)
    def get_dispatch_deps(
        self,
        bar_repository: BarRepository,
        backtest_repository: BacktestRepository,
        backtest_order_repository: BacktestOrderRepository,
        backtest_trade_repository: BacktestTradeRepository,
    ) -> BacktestDispatchDeps:
        return BacktestDispatchDeps(
            bar_repo=bar_repository,
            backtest_repo=backtest_repository,
            order_repo=backtest_order_repository,
            trade_repo=backtest_trade_repository,
        )

    @provide(scope=Scope.APP)
    def get_backtest_execution_service(
        self,
        dispatch_deps: BacktestDispatchDeps,
        backtest_repository: BacktestRepository,
    ) -> BacktestExecutionService:
        return BacktestExecutionService(dispatch_deps, backtest_repository)
