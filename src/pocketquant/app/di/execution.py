"""Execution engine providers — shared strategy/order/position/risk app-services.

OrderAppService and PositionAppService need async post-init (load state from DB).
StrategyAppService uses a generator factory for start/stop lifecycle.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from pocketquant.app.di.broker_factory import BrokerFactory
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.engine.app_services.order_app_service import OrderAppService
from pocketquant.engine.app_services.position_app_service import PositionAppService
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService
from pocketquant.engine.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)
from pocketquant.engine.handlers.risk.check_risk.handler import RiskCheckHandler


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
