"""Infrastructure service providers.

JobScheduler uses a generator factory for start/shutdown lifecycle.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from src.common.health import HealthCoordinator
from src.config import Settings
from src.features.risk.check_risk.handler import RiskCheckHandler
from src.infrastructure.brokers import BrokerFactory
from src.infrastructure.scheduling.scheduler import JobScheduler
from src.infrastructure.tradingview import TradingViewProvider


class InfrastructureProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_job_scheduler(
        self, settings: Settings
    ) -> AsyncIterator[JobScheduler]:
        """Initialize and start scheduler. Shutdown on app exit."""
        scheduler = JobScheduler()
        if settings.enable_jobs:
            scheduler.initialize(settings)
            scheduler.start()
        yield scheduler
        if settings.enable_jobs:
            scheduler.shutdown(wait=True)

    @provide(scope=Scope.APP)
    def get_tv_provider(self, settings: Settings) -> TradingViewProvider:
        return TradingViewProvider(settings=settings)

    broker_factory = provide(BrokerFactory, scope=Scope.APP)
    risk_handler = provide(RiskCheckHandler, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_health_coordinator(self) -> HealthCoordinator:
        return HealthCoordinator(timeout=5.0)
