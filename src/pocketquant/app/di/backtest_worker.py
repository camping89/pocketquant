"""Backtest worker provider — queue worker + shared dispatch deps.

App-only runtime concern: the headless app drains backtest_requests. bff never
includes this provider (it only enqueues requests via the repo).
"""

from dishka import Provider, Scope, provide

from pocketquant.backtest.workers.backtest_dispatch import BacktestDispatchDeps
from pocketquant.backtest.workers.backtest_request_worker import BacktestRequestWorker
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService


class BacktestWorkerProvider(Provider):
    @provide(scope=Scope.APP)
    def get_dispatch_deps(
        self,
        event_bus: EventBus,
        bar_repository: BarRepository,
        backtest_repository: BacktestRepository,
        backtest_order_repository: BacktestOrderRepository,
        backtest_trade_repository: BacktestTradeRepository,
        strategy_app_service: StrategyAppService,
        subscription_repository: SubscriptionRepository,
    ) -> BacktestDispatchDeps:
        return BacktestDispatchDeps(
            event_bus=event_bus,
            bar_repo=bar_repository,
            backtest_repo=backtest_repository,
            order_repo=backtest_order_repository,
            trade_repo=backtest_trade_repository,
            strategy_app_service=strategy_app_service,
            subscription_repo=subscription_repository,
        )

    @provide(scope=Scope.APP)
    def get_backtest_worker(
        self,
        backtest_request_repository: BacktestRequestRepository,
        dispatch_deps: BacktestDispatchDeps,
    ) -> BacktestRequestWorker:
        return BacktestRequestWorker(backtest_request_repository, dispatch_deps)
