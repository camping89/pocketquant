"""Market data service providers."""

from dishka import Provider, Scope, provide

from src.application.market_data.bar_app_service import BarAppService
from src.application.market_data.quote_app_service import QuoteAppService
from src.config import Settings
from src.persistence.redis import Cache
from src.persistence.repositories.ohlcv_repository import OHLCVRepository


class MarketDataProvider(Provider):
    @provide(scope=Scope.APP)
    def get_bar_manager(
        self, cache: Cache, ohlcv_repository: OHLCVRepository
    ) -> BarAppService:
        return BarAppService(cache=cache, ohlcv_repository=ohlcv_repository)

    @provide(scope=Scope.APP)
    def get_quote_service(
        self, settings: Settings, cache: Cache, bar_manager: BarAppService
    ) -> QuoteAppService:
        return QuoteAppService(settings=settings, cache=cache, bar_manager=bar_manager)
