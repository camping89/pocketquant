"""Market data service providers."""

from dishka import Provider, Scope, provide

from pocketquant.app.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.app.market_data.app_services.ws_subscription_manager import WsSubscriptionManager
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.interfaces import IRealtimeQuoteProvider
from pocketquant.core.infra.binance.binance_websocket_client import (
    BinanceWebSocketClient,
)
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService


class MarketDataProvider(Provider):
    @provide(scope=Scope.APP)
    def get_bar_manager(
        self, cache: Cache, bar_repository: BarRepository, event_bus: EventBus
    ) -> BarAppService:
        return BarAppService(cache=cache, bar_repository=bar_repository, event_bus=event_bus)

    @provide(scope=Scope.APP)
    def get_realtime_quote_provider(self) -> IRealtimeQuoteProvider:
        """Singleton WS client shared by QuoteAppService, WsSubscriptionManager, status handler."""
        return BinanceWebSocketClient()  # type: ignore[return-value]  # Protocol satisfied structurally

    @provide(scope=Scope.APP)
    def get_quote_service(
        self,
        settings: Settings,
        cache: Cache,
        bar_manager: BarAppService,
        provider: IRealtimeQuoteProvider,
    ) -> QuoteAppService:
        return QuoteAppService(
            settings=settings, cache=cache, bar_manager=bar_manager, provider=provider
        )

    @provide(scope=Scope.APP)
    def get_ws_subscription_manager(
        self,
        provider: IRealtimeQuoteProvider,
        tracked_symbol_repo: TrackedSymbolRepository,
        quote_app_service: QuoteAppService,
    ) -> WsSubscriptionManager:
        return WsSubscriptionManager(
            provider=provider,
            tracked_symbol_repo=tracked_symbol_repo,
            quote_app_service=quote_app_service,
        )
