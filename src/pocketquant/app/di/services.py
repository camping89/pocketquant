"""Services provider: market-data, execution, trading, backtest and feature services.

Routes inject the feature services directly via FromDishka. OrderAppService
and PositionAppService need async post-init (load state from DB);
StrategyAppService uses a generator factory for start/stop lifecycle.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from pocketquant.app.di.adapters import BrokerFactory
from pocketquant.app.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.app.market_data.app_services.ws_subscription_manager import WsSubscriptionManager
from pocketquant.backtest.backtest_command_service import BacktestCommandService
from pocketquant.backtest.backtest_execution_service import BacktestExecutionService
from pocketquant.backtest.backtest_query_service import BacktestQueryService
from pocketquant.backtest.backtest_stats_service import BacktestStatsService
from pocketquant.backtest.workers.backtest_dispatch import BacktestDispatchDeps
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.redis import Cache
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
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.engine.app_services.order_app_service import OrderAppService
from pocketquant.engine.app_services.position_app_service import PositionAppService
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService
from pocketquant.engine.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)
from pocketquant.engine.handlers.risk.check_risk.handler import RiskCheckHandler
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService
from pocketquant.engine.market_data.ohlcv_service import OhlcvService
from pocketquant.engine.market_data.quotes_service import QuoteQueryService
from pocketquant.engine.market_data.symbols_service import SymbolQueryService
from pocketquant.engine.market_data.sync_policy import SyncPolicies
from pocketquant.engine.market_data.sync_service import SyncService
from pocketquant.engine.market_data.sync_status_service import SyncStatusQueryService
from pocketquant.engine.market_data.tracked_symbols_backfill import TrackedSymbolBackfillService
from pocketquant.engine.market_data.tracked_symbols_service import TrackedSymbolService
from pocketquant.engine.orders_positions_service import OrderPositionQueryService
from pocketquant.engine.strategy_command_service import StrategyCommandService
from pocketquant.engine.strategy_query_service import StrategyQueryService


class ServicesProvider(Provider):
    # SyncService is used by scheduler jobs (sync_1m, sync_backfill, repair) directly —
    sync_service = provide(SyncService, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_bar_manager(
        self, cache: Cache, bar_repository: BarRepository, event_bus: EventBus
    ) -> BarAppService:
        return BarAppService(cache=cache, bar_repository=bar_repository, event_bus=event_bus)

    @provide(scope=Scope.APP)
    def get_quote_service(
        self,
        settings: Settings,
        cache: Cache,
        bar_manager: BarAppService,
        policies: SyncPolicies,
    ) -> QuoteAppService:
        return QuoteAppService(
            settings=settings, cache=cache, bar_manager=bar_manager, policies=policies
        )

    @provide(scope=Scope.APP)
    def get_ws_subscription_manager(
        self,
        policies: SyncPolicies,
        tracked_symbol_repo: TrackedSymbolRepository,
        quote_app_service: QuoteAppService,
    ) -> WsSubscriptionManager:
        return WsSubscriptionManager(
            policies=policies,
            tracked_symbol_repo=tracked_symbol_repo,
            quote_app_service=quote_app_service,
        )

    risk_handler = provide(RiskCheckHandler, scope=Scope.APP)

    @provide(scope=Scope.APP)
    async def get_order_manager(
        self, event_bus: EventBus, order_repository: OrderRepository
    ) -> OrderAppService:
        manager = OrderAppService(event_bus, order_repository)
        await manager.load_pending_orders()
        return manager

    @provide(scope=Scope.APP)
    async def get_position_tracker(
        self, event_bus: EventBus, position_repository: PositionRepository
    ) -> PositionAppService:
        tracker = PositionAppService(event_bus, position_repository)
        await tracker.start()
        return tracker

    @provide(scope=Scope.APP)
    async def get_strategy_engine(
        self,
        event_bus: EventBus,
        broker_factory: BrokerFactory,
        order_app_service: OrderAppService,
        position_app_service: PositionAppService,
        risk_check_handler: RiskCheckHandler,
        settings: Settings,
    ) -> AsyncIterator[StrategyAppService]:
        engine = StrategyAppService(
            event_bus=event_bus,
            broker_factory=broker_factory,
            order_app_service=order_app_service,
            position_app_service=position_app_service,
            risk_check_handler=risk_check_handler,
            default_broker_config={
                "initial_balance": settings.paper_initial_balance,
                "slippage_percent": settings.paper_slippage_percent,
                "api_key": settings.okx_api_key,
                "api_secret": settings.okx_api_secret,
                "passphrase": settings.okx_passphrase,
                "demo": settings.okx_demo_mode,
            },
        )
        await engine.start()
        yield engine
        await engine.stop()

    @provide(scope=Scope.APP)
    def get_reconcile_service(
        self,
        subscription_repository: SubscriptionRepository,
        strategy_app_service: StrategyAppService,
        settings: Settings,
    ) -> StrategyReconcileService:
        return StrategyReconcileService(
            subscription_repository,
            strategy_app_service,
            interval_s=settings.reconcile_interval_seconds,
        )

    strategy_command_service = provide(StrategyCommandService, scope=Scope.APP)
    strategy_query_service = provide(StrategyQueryService, scope=Scope.APP)
    order_position_query_service = provide(OrderPositionQueryService, scope=Scope.APP)

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

    tracked_symbol_service = provide(TrackedSymbolService, scope=Scope.APP)
    tracked_symbol_backfill_service = provide(TrackedSymbolBackfillService, scope=Scope.APP)
    ohlcv_service = provide(OhlcvService, scope=Scope.APP)
    quote_query_service = provide(QuoteQueryService, scope=Scope.APP)
    sync_status_query_service = provide(SyncStatusQueryService, scope=Scope.APP)
    symbol_query_service = provide(SymbolQueryService, scope=Scope.APP)
    backtest_command_service = provide(BacktestCommandService, scope=Scope.APP)
    backtest_query_service = provide(BacktestQueryService, scope=Scope.APP)
    backtest_stats_service = provide(BacktestStatsService, scope=Scope.APP)
