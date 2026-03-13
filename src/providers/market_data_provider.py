"""Market data service providers."""

from dishka import Provider, Scope, provide

from src.application.market_data.bar_manager import BarManager
from src.application.market_data.quote_service import QuoteService
from src.config import Settings
from src.persistence.redis import Cache
from src.persistence.repositories.ohlcv_repository import OHLCVRepository


class MarketDataProvider(Provider):
    @provide(scope=Scope.APP)
    def get_bar_manager(
        self, cache: Cache, ohlcv_repository: OHLCVRepository
    ) -> BarManager:
        return BarManager(cache=cache, ohlcv_repository=ohlcv_repository)

    @provide(scope=Scope.APP)
    def get_quote_service(
        self, settings: Settings, cache: Cache, bar_manager: BarManager
    ) -> QuoteService:
        return QuoteService(settings=settings, cache=cache, bar_manager=bar_manager)
