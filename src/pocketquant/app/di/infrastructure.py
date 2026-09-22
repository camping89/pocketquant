from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.infra.binance.binance_adapter import BinanceAdapter
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    RoutingDataProviderAdapter,
)
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.core.infra.tradingview.tradingview_adapter import TradingViewAdapter
from pocketquant.core.infra.tradingview.tvdatafeed_client import TvDatafeedClient


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
    def get_data_provider(
        self,
        settings: Settings,
        symbol_lookup: SymbolLookupHelper,
        calendar_factory: TradingCalendarFactory,
    ) -> IDataProviderPort:
        # Adding a provider is one entry here plus one config entry. The routing
        # adapter implements the same port, so every consumer above it is
        # unchanged, and the asset-class map in Settings decides who serves what.
        return RoutingDataProviderAdapter(
            providers={
                "binance": BinanceAdapter(settings=settings),
                "tradingview": TradingViewAdapter(
                    client=TvDatafeedClient(settings=settings),
                    settings=settings,
                    calendar_factory=calendar_factory,
                ),
            },
            settings=settings,
            symbol_lookup=symbol_lookup,
        )

    broker_factory = provide(BrokerFactory, scope=Scope.APP)
    trading_calendar_factory = provide(TradingCalendarFactory, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_health_coordinator(self) -> HealthCoordinator:
        return HealthCoordinator(timeout=5.0)
