"""CQRS handler construction and registration.

Replaces the string-based getattr/resolve pattern from the old container.
Each handler is constructed with explicit dependencies from Services.
"""

from src.common.mediator.handler_registry import HandlerRegistry
from src.features.backtesting.get_optimization.handler import GetOptimizationHandler
from src.features.backtesting.get_result.handler import GetBacktestHandler
from src.features.backtesting.list_results.handler import ListBacktestsHandler
from src.features.backtesting.optimize.handler import RunOptimizationHandler
from src.features.backtesting.run.handler import RunBacktestHandler
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
from src.features.market_data.status.get_sync_status.handler import (
    GetSyncStatusHandler,
)
from src.features.market_data.sync.sync_bulk.handler import BulkSyncHandler
from src.features.market_data.sync.sync_one.handler import SyncSymbolHandler
from src.features.strategy.get_all.handler import GetStrategiesHandler
from src.features.strategy.get_one.handler import GetStrategyHandler
from src.features.strategy.load.handler import LoadStrategyHandler
from src.features.strategy.start.handler import StartStrategyHandler
from src.features.strategy.stop.handler import StopStrategyHandler
from src.features.trading.get_order.handler import GetOrderHandler
from src.features.trading.get_position.handler import GetPositionHandler
from src.features.trading.list_orders.handler import ListOrdersHandler
from src.features.trading.list_positions.handler import ListPositionsHandler
from src.services import Services


def register_all_handlers(services: Services) -> None:
    """Register all CQRS handlers with mediator using explicit constructors."""
    registry = HandlerRegistry()

    # Shared instance for BulkSyncHandler
    sync_symbol_handler = SyncSymbolHandler(
        provider=services.tv_provider,
        event_bus=services.event_bus,
        cache=services.cache,
        ohlcv_repository=services.ohlcv_repository,
        symbol_repository=services.symbol_repository,
        sync_status_repository=services.sync_status_repository,
    )

    handlers = [
        # Market data (13)
        sync_symbol_handler,
        BulkSyncHandler(sync_handler=sync_symbol_handler),
        GetOHLCVHandler(
            cache=services.cache, ohlcv_repository=services.ohlcv_repository
        ),
        StartQuoteFeedHandler(quote_service=services.quote_service),
        StopQuoteFeedHandler(quote_service=services.quote_service),
        SubscribeHandler(quote_service=services.quote_service),
        UnsubscribeHandler(
            quote_service=services.quote_service, cache=services.cache
        ),
        GetLatestQuoteHandler(cache=services.cache),
        GetAllQuotesHandler(
            quote_service=services.quote_service, cache=services.cache
        ),
        GetSyncStatusHandler(
            sync_status_repository=services.sync_status_repository
        ),
        GetSymbolSyncStatusHandler(
            sync_status_repository=services.sync_status_repository
        ),
        GetQuoteServiceStatusHandler(quote_service=services.quote_service),
        ListSymbolsHandler(symbol_repository=services.symbol_repository),
        # Trading (4)
        ListOrdersHandler(order_manager=services.order_manager),
        GetOrderHandler(order_manager=services.order_manager),
        ListPositionsHandler(position_tracker=services.position_tracker),
        GetPositionHandler(position_tracker=services.position_tracker),
        # Strategy (5)
        LoadStrategyHandler(engine=services.strategy_engine),
        StartStrategyHandler(engine=services.strategy_engine),
        StopStrategyHandler(engine=services.strategy_engine),
        GetStrategiesHandler(engine=services.strategy_engine),
        GetStrategyHandler(engine=services.strategy_engine),
        # Backtesting (5)
        RunBacktestHandler(
            event_bus=services.event_bus,
            strategy_engine=services.strategy_engine,
            backtest_repository=services.backtest_repository,
            ohlcv_repository=services.ohlcv_repository,
        ),
        RunOptimizationHandler(
            event_bus=services.event_bus,
            strategy_engine=services.strategy_engine,
            backtest_repository=services.backtest_repository,
            ohlcv_repository=services.ohlcv_repository,
            optimization_repository=services.optimization_repository,
        ),
        GetBacktestHandler(backtest_repository=services.backtest_repository),
        GetOptimizationHandler(
            optimization_repository=services.optimization_repository
        ),
        ListBacktestsHandler(
            backtest_repository=services.backtest_repository
        ),
    ]

    registry.register_all(services.mediator, handlers)
