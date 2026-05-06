"""Market data service providers."""

from dishka import Provider, Scope, provide
from pocketquant.api.market_data.app_services.bar_app_service import BarAppService
from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.api.market_data.app_services.ws_subscription_manager import WsSubscriptionManager
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.infrastructure.tradingview import TradingViewWebSocketClient
from pocketquant.core.persistence.redis import Cache
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.persistence.repositories.tracked_symbol_repository import TrackedSymbolRepository


class MarketDataProvider(Provider):
    @provide(scope=Scope.APP)
    def get_bar_manager(
        self, cache: Cache, bar_repository: BarRepository, event_bus: EventBus
    ) -> BarAppService:
        return BarAppService(cache=cache, bar_repository=bar_repository, event_bus=event_bus)

    @provide(scope=Scope.APP)
    def get_ws_client(self) -> TradingViewWebSocketClient:
        """Singleton WS client shared by QuoteAppService, WsSubscriptionManager, and status handler."""
        return TradingViewWebSocketClient()

    @provide(scope=Scope.APP)
    def get_quote_service(
        self, settings: Settings, cache: Cache, bar_manager: BarAppService, provider: TradingViewWebSocketClient
    ) -> QuoteAppService:
        return QuoteAppService(
            settings=settings, cache=cache, bar_manager=bar_manager, provider=provider
        )

    @provide(scope=Scope.APP)
    def get_ws_subscription_manager(
        self,
        provider: TradingViewWebSocketClient,
        tracked_symbol_repo: TrackedSymbolRepository,
        quote_app_service: QuoteAppService,
    ) -> WsSubscriptionManager:
        return WsSubscriptionManager(
            provider=provider,
            tracked_symbol_repo=tracked_symbol_repo,
            quote_app_service=quote_app_service,
        )
