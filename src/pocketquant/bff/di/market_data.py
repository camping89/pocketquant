"""Market data providers for bff — BarAppService + IDataProvider only.

No WS runtime: bff carries no QuoteAppService, no WsSubscriptionManager,
no IRealtimeQuoteProvider. BarAppService reads Cache (live bar written by app's
WS feed) with DB fallback — bff-safe by design.
"""

from dishka import Provider, Scope, provide

from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.interfaces import IDataProvider
from pocketquant.core.infra.binance.binance_client import BinanceClient
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService


class BffMarketDataProvider(Provider):
    @provide(scope=Scope.APP)
    def get_bar_service(
        self, cache: Cache, bar_repository: BarRepository, event_bus: EventBus
    ) -> BarAppService:
        return BarAppService(cache=cache, bar_repository=bar_repository, event_bus=event_bus)

    @provide(scope=Scope.APP)
    def get_data_provider(self, settings: Settings) -> IDataProvider:
        """REST data provider for backfill route — no WS streaming."""
        return BinanceClient(settings=settings)

    @provide(scope=Scope.APP)
    def get_health_coordinator(self) -> HealthCoordinator:
        return HealthCoordinator(timeout=5.0)
