"""Trading service providers with async lifecycle.

OrderAppService and PositionAppService need async post-init (load state from DB).
StrategyAppService uses a generator factory for start/stop lifecycle.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from pocketquant.api.di.broker_factory import BrokerFactory
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.trading.app_services.order_app_service import OrderAppService
from pocketquant.trading.app_services.position_app_service import PositionAppService
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.handlers.risk.check_risk.handler import RiskCheckHandler
from pocketquant.infrastructure.persistence.repositories.order_repository import OrderRepository
from pocketquant.infrastructure.persistence.repositories.position_repository import PositionRepository


class TradingProvider(Provider):
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
        """Create, start, and yield StrategyAppService. Stop on app shutdown."""
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
