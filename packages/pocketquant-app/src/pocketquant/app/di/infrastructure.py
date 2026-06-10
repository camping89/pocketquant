"""Infrastructure service providers.

JobScheduler uses a generator factory for start/shutdown lifecycle.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from pocketquant.app.di.broker_factory import BrokerFactory
from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.interfaces import IDataProvider
from pocketquant.core.market_data.binance.binance_client import BinanceClient
from pocketquant.core.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.scheduling.scheduler import JobScheduler


class InfrastructureProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_job_scheduler(
        self, settings: Settings, history_repo: JobHistoryRepository
    ) -> AsyncIterator[JobScheduler]:
        """Initialize and start scheduler. Shutdown on app exit."""
        scheduler = JobScheduler(history_repo=history_repo)
        if settings.enable_jobs:
            scheduler.initialize(settings)
            scheduler.start()
        yield scheduler
        if settings.enable_jobs:
            scheduler.shutdown(wait=True)

    @provide(scope=Scope.APP)
    def get_data_provider(self, settings: Settings) -> IDataProvider:
        return BinanceClient(settings=settings)

    broker_factory = provide(BrokerFactory, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_health_coordinator(self) -> HealthCoordinator:
        return HealthCoordinator(timeout=5.0)
