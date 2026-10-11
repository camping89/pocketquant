from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from pocketquant.app.di.broker_factory import BrokerFactory
from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.config import Settings
from pocketquant.core.infra.binance.binance_client import BinanceClient
from pocketquant.core.infra.binance.binance_websocket_client import BinanceWebSocketClient
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.market_data.sync_policy import SyncPolicies, binance_policy


class InfrastructureProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_job_scheduler(
        self, settings: Settings, history_repo: JobHistoryRepository
    ) -> AsyncIterator[JobScheduler]:
        scheduler = JobScheduler(history_repo=history_repo)
        if settings.enable_jobs:
            scheduler.initialize(settings)
            scheduler.start()
        yield scheduler
        if settings.enable_jobs:
            scheduler.shutdown(wait=True)

    @provide(scope=Scope.APP)
    def get_sync_policies(self, settings: Settings) -> SyncPolicies:
        return SyncPolicies(
            [
                binance_policy(
                    data_provider=BinanceClient(settings=settings),
                    quote_provider=BinanceWebSocketClient(),
                )
            ]
        )

    broker_factory = provide(BrokerFactory, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_health_coordinator(self) -> HealthCoordinator:
        return HealthCoordinator(timeout=5.0)
