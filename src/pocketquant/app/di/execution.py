"""Execution engine providers — shared strategy/order/position/risk app-services.

OrderAppService and PositionAppService need async post-init (load state from DB).
StrategyAppService uses a generator factory for start/stop lifecycle.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.live.live_metrics_query_service import LiveMetricsQueryService
from pocketquant.engine.live.live_trade_collector import LiveTradeCollector
from pocketquant.engine.live.strategy_reconcile_app_service import (
    StrategyReconcileAppService,
)
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService


class ExecutionProvider(Provider):
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
                "slippage_bps": settings.paper_slippage_bps,
                "commission_bps": settings.paper_commission_bps,
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
    ) -> StrategyReconcileAppService:
        return StrategyReconcileAppService(
            subscription_repository,
            strategy_app_service,
            interval_s=settings.reconcile_interval_seconds,
        )

    @provide(scope=Scope.APP)
    def get_live_trade_collector(
        self,
        event_bus: EventBus,
        trade_repository: TradeRepository,
        strategy_app_service: StrategyAppService,
    ) -> LiveTradeCollector:
        return LiveTradeCollector(event_bus, trade_repository, strategy_app_service)

    @provide(scope=Scope.APP)
    def get_live_metrics_query_service(
        self,
        trade_repository: TradeRepository,
        settings: Settings,
    ) -> LiveMetricsQueryService:
        return LiveMetricsQueryService(trade_repository, baseline=settings.paper_initial_balance)
