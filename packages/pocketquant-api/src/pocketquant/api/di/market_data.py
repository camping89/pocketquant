"""Market data service providers."""

from dishka import Provider, Scope, provide
from pocketquant.api.market_data.app_services.bar_app_service import BarAppService
from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.infrastructure.tradingview import TradingViewWebSocketClient
from pocketquant.core.persistence.redis import Cache
from pocketquant.core.persistence.repositories.bar_repository import BarRepository


class MarketDataProvider(Provider):
    @provide(scope=Scope.APP)
    def get_bar_manager(
        self, cache: Cache, bar_repository: BarRepository, event_bus: EventBus
    ) -> BarAppService:
        return BarAppService(cache=cache, bar_repository=bar_repository, event_bus=event_bus)

    @provide(scope=Scope.APP)
    def get_quote_service(
        self, settings: Settings, cache: Cache, bar_manager: BarAppService
    ) -> QuoteAppService:
        provider = TradingViewWebSocketClient()
        return QuoteAppService(
            settings=settings, cache=cache, bar_manager=bar_manager, provider=provider
        )
