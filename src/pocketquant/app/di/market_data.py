from dishka import Provider, Scope, provide

from pocketquant.app.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.app.market_data.app_services.ws_subscription_app_service import (
    WsSubscriptionAppService,
)
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.binance.binance_websocket_client import (
    BinanceWebSocketClient,
)
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService
from pocketquant.engine.market_data.sync_service import SyncService


class MarketDataProvider(Provider):
    # SyncService is used by scheduler jobs (sync_1m, sync_backfill, repair) directly —
    sync_service = provide(SyncService, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_bar_manager(
        self, cache: Cache, bar_repository: BarRepository, event_bus: EventBus
    ) -> BarAppService:
        return BarAppService(cache=cache, bar_repository=bar_repository, event_bus=event_bus)

    @provide(scope=Scope.APP)
    def get_realtime_quote_provider(self) -> IRealtimeQuoteProviderPort:
        return BinanceWebSocketClient()  # type: ignore[return-value]  # Protocol satisfied structurally

    @provide(scope=Scope.APP)
    def get_quote_service(
        self,
        settings: Settings,
        cache: Cache,
        bar_manager: BarAppService,
        provider: IRealtimeQuoteProviderPort,
    ) -> QuoteAppService:
        return QuoteAppService(
            settings=settings, cache=cache, bar_manager=bar_manager, provider=provider
        )

    @provide(scope=Scope.APP)
    def get_ws_subscription_manager(
        self,
        provider: IRealtimeQuoteProviderPort,
        tracked_symbol_repo: TrackedSymbolRepository,
        quote_app_service: QuoteAppService,
    ) -> WsSubscriptionAppService:
        return WsSubscriptionAppService(
            provider=provider,
            tracked_symbol_repo=tracked_symbol_repo,
            quote_app_service=quote_app_service,
        )
