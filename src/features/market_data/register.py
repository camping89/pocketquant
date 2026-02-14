"""Auto-register all market_data CQRS handlers with mediator."""

from src.common.mediator import HandlerRegistry, Mediator
from src.common.messaging import EventBus
from src.config import Settings
from src.features.market_data.list_symbols.handler import ListSymbolsHandler
from src.features.market_data.ohlcv.get_ohlcv.handler import GetOHLCVHandler
from src.features.market_data.quotes.get_all.handler import GetAllQuotesHandler
from src.features.market_data.quotes.get_latest.handler import GetLatestQuoteHandler
from src.features.market_data.quotes.start_feed.handler import StartQuoteFeedHandler
from src.features.market_data.quotes.stop_feed.handler import StopQuoteFeedHandler
from src.features.market_data.quotes.subscribe.handler import SubscribeHandler
from src.features.market_data.quotes.unsubscribe.handler import UnsubscribeHandler
from src.features.market_data.status.get_quote_service_status.handler import (
    GetQuoteServiceStatusHandler,
)
from src.features.market_data.status.get_symbol_sync_status.handler import (
    GetSymbolSyncStatusHandler,
)
from src.features.market_data.status.get_sync_status.handler import GetSyncStatusHandler
from src.features.market_data.sync.sync_bulk.handler import BulkSyncHandler
from src.features.market_data.sync.sync_one.handler import SyncSymbolHandler
from src.infrastructure.tradingview import TradingViewProvider


def register_handlers(
    mediator: Mediator,
    settings: Settings,
    tv_provider: TradingViewProvider,
    event_bus: EventBus,
) -> None:
    """Register all market_data handlers with mediator."""
    sync_handler = SyncSymbolHandler(tv_provider, event_bus)

    registry = HandlerRegistry()
    registry.register_all(
        mediator,
        [
            # Sync
            sync_handler,
            BulkSyncHandler(sync_handler),
            # OHLCV
            GetOHLCVHandler(),
            # Quotes
            StartQuoteFeedHandler(settings),
            StopQuoteFeedHandler(settings),
            SubscribeHandler(settings),
            UnsubscribeHandler(settings),
            GetLatestQuoteHandler(),
            GetAllQuotesHandler(settings),
            # Status
            GetSyncStatusHandler(),
            GetSymbolSyncStatusHandler(),
            GetQuoteServiceStatusHandler(settings),
            # Symbols
            ListSymbolsHandler(),
        ],
    )
