"""CQRS handler providers — all 27 handlers as APP-scoped singletons.

Handlers are resolved by dishka via __init__ type hints and registered
with Mediator in pocketquant.api.di.container:register_handlers().
"""

from dishka import Provider, Scope, provide
from pocketquant.api.market_data.handlers.list_symbols.handler import ListSymbolsHandler
from pocketquant.api.market_data.handlers.ohlcv.get_ohlcv.handler import GetOHLCVHandler
from pocketquant.api.market_data.handlers.quotes.get_all.handler import GetAllQuotesHandler
from pocketquant.api.market_data.handlers.quotes.get_latest.handler import GetLatestQuoteHandler
from pocketquant.api.market_data.handlers.quotes.get_status.handler import GetQuotesStatusHandler
from pocketquant.api.market_data.handlers.quotes.subscribe.handler import SubscribeHandler
from pocketquant.api.market_data.handlers.quotes.unsubscribe.handler import UnsubscribeHandler
from pocketquant.api.market_data.handlers.status.get_quote_service_status.handler import (
    GetQuoteServiceStatusHandler,
)
from pocketquant.api.market_data.handlers.status.get_symbol_sync_status.handler import (
    GetSymbolSyncStatusHandler,
)
from pocketquant.api.market_data.handlers.status.get_sync_status.handler import (
    GetSyncStatusHandler,
)
from pocketquant.api.market_data.handlers.sync.sync_bulk.handler import BulkSyncHandler
from pocketquant.api.market_data.handlers.sync.sync_one.handler import SyncSymbolHandler
from pocketquant.api.market_data.handlers.tracked_symbols.add.handler import AddTrackedSymbolHandler
from pocketquant.api.market_data.handlers.tracked_symbols.list_all.handler import (
    ListTrackedSymbolsHandler,
)
from pocketquant.api.market_data.handlers.tracked_symbols.remove.handler import (
    RemoveTrackedSymbolHandler,
)
from pocketquant.api.market_data.handlers.tracked_symbols.update.handler import (
    UpdateTrackedSymbolHandler,
)
from pocketquant.backtest.handlers.get_optimization.handler import GetOptimizationHandler
from pocketquant.backtest.handlers.get_result.handler import GetBacktestHandler
from pocketquant.backtest.handlers.list_results.handler import ListBacktestsHandler
from pocketquant.backtest.handlers.optimize.handler import RunOptimizationHandler
from pocketquant.backtest.handlers.run.handler import RunBacktestHandler
from pocketquant.trading.handlers.strategy.add_symbol.handler import AddSymbolHandler
from pocketquant.trading.handlers.strategy.delete.handler import DeleteStrategyHandler
from pocketquant.trading.handlers.strategy.get_all.handler import GetStrategiesHandler
from pocketquant.trading.handlers.strategy.get_one.handler import GetStrategyHandler
from pocketquant.trading.handlers.strategy.get_positions.handler import (
    GetStrategyPositionsHandler,
)
from pocketquant.trading.handlers.strategy.get_subscription_backtest.handler import (
    GetSubscriptionBacktestHandler,
)
from pocketquant.trading.handlers.strategy.get_trades.handler import (
    GetStrategyTradesHandler,
)
from pocketquant.trading.handlers.strategy.list_symbols.handler import (
    ListSymbolsHandler as ListStrategySymbolsHandler,
)
from pocketquant.trading.handlers.strategy.load.handler import LoadStrategyHandler
from pocketquant.trading.handlers.strategy.remove_symbol.handler import RemoveSymbolHandler
from pocketquant.trading.handlers.strategy.run_all_backtests.handler import RunAllBacktestsHandler
from pocketquant.trading.handlers.strategy.start.handler import StartStrategyHandler
from pocketquant.trading.handlers.strategy.stop.handler import StopStrategyHandler
from pocketquant.trading.handlers.trading.get_order.handler import GetOrderHandler
from pocketquant.trading.handlers.trading.get_position.handler import GetPositionHandler
from pocketquant.trading.handlers.trading.list_orders.handler import ListOrdersHandler
from pocketquant.trading.handlers.trading.list_positions.handler import ListPositionsHandler


class HandlerProvider(Provider):
    # Market data (16 — includes tracked_symbols CRUD; start_feed/stop_feed removed)
    list_tracked_symbols_handler = provide(ListTrackedSymbolsHandler, scope=Scope.APP)
    add_tracked_symbol_handler = provide(AddTrackedSymbolHandler, scope=Scope.APP)
    update_tracked_symbol_handler = provide(UpdateTrackedSymbolHandler, scope=Scope.APP)
    remove_tracked_symbol_handler = provide(RemoveTrackedSymbolHandler, scope=Scope.APP)
    sync_symbol_handler = provide(SyncSymbolHandler, scope=Scope.APP)
    bulk_sync_handler = provide(BulkSyncHandler, scope=Scope.APP)
    get_ohlcv_handler = provide(GetOHLCVHandler, scope=Scope.APP)
    subscribe_handler = provide(SubscribeHandler, scope=Scope.APP)
    unsubscribe_handler = provide(UnsubscribeHandler, scope=Scope.APP)
    get_latest_quote_handler = provide(GetLatestQuoteHandler, scope=Scope.APP)
    get_all_quotes_handler = provide(GetAllQuotesHandler, scope=Scope.APP)
    get_quotes_status_handler = provide(GetQuotesStatusHandler, scope=Scope.APP)
    get_sync_status_handler = provide(GetSyncStatusHandler, scope=Scope.APP)
    get_symbol_sync_status_handler = provide(GetSymbolSyncStatusHandler, scope=Scope.APP)
    get_quote_service_status_handler = provide(GetQuoteServiceStatusHandler, scope=Scope.APP)
    list_symbols_handler = provide(ListSymbolsHandler, scope=Scope.APP)

    # Trading (4)
    list_orders_handler = provide(ListOrdersHandler, scope=Scope.APP)
    get_order_handler = provide(GetOrderHandler, scope=Scope.APP)
    list_positions_handler = provide(ListPositionsHandler, scope=Scope.APP)
    get_position_handler = provide(GetPositionHandler, scope=Scope.APP)

    # Strategy (11)
    load_strategy_handler = provide(LoadStrategyHandler, scope=Scope.APP)
    start_strategy_handler = provide(StartStrategyHandler, scope=Scope.APP)
    stop_strategy_handler = provide(StopStrategyHandler, scope=Scope.APP)
    get_strategies_handler = provide(GetStrategiesHandler, scope=Scope.APP)
    get_strategy_handler = provide(GetStrategyHandler, scope=Scope.APP)
    add_symbol_handler = provide(AddSymbolHandler, scope=Scope.APP)
    remove_symbol_handler = provide(RemoveSymbolHandler, scope=Scope.APP)
    list_strategy_symbols_handler = provide(ListStrategySymbolsHandler, scope=Scope.APP)
    run_all_backtests_handler = provide(RunAllBacktestsHandler, scope=Scope.APP)
    get_subscription_backtest_handler = provide(GetSubscriptionBacktestHandler, scope=Scope.APP)
    get_strategy_positions_handler = provide(GetStrategyPositionsHandler, scope=Scope.APP)
    get_strategy_trades_handler = provide(GetStrategyTradesHandler, scope=Scope.APP)
    delete_strategy_handler = provide(DeleteStrategyHandler, scope=Scope.APP)

    # Backtesting (5)
    run_backtest_handler = provide(RunBacktestHandler, scope=Scope.APP)
    run_optimization_handler = provide(RunOptimizationHandler, scope=Scope.APP)
    get_backtest_handler = provide(GetBacktestHandler, scope=Scope.APP)
    get_optimization_handler = provide(GetOptimizationHandler, scope=Scope.APP)
    list_backtests_handler = provide(ListBacktestsHandler, scope=Scope.APP)


# All handler types — used by register_handlers() in pocketquant.api.di.container
ALL_HANDLER_TYPES: list[type] = [
    ListTrackedSymbolsHandler,
    AddTrackedSymbolHandler,
    UpdateTrackedSymbolHandler,
    RemoveTrackedSymbolHandler,
    SyncSymbolHandler,
    BulkSyncHandler,
    GetOHLCVHandler,
    SubscribeHandler,
    UnsubscribeHandler,
    GetLatestQuoteHandler,
    GetAllQuotesHandler,
    GetQuotesStatusHandler,
    GetSyncStatusHandler,
    GetSymbolSyncStatusHandler,
    GetQuoteServiceStatusHandler,
    ListSymbolsHandler,
    ListOrdersHandler,
    GetOrderHandler,
    ListPositionsHandler,
    GetPositionHandler,
    LoadStrategyHandler,
    StartStrategyHandler,
    StopStrategyHandler,
    GetStrategiesHandler,
    GetStrategyHandler,
    AddSymbolHandler,
    RemoveSymbolHandler,
    ListStrategySymbolsHandler,
    RunAllBacktestsHandler,
    GetSubscriptionBacktestHandler,
    GetStrategyPositionsHandler,
    GetStrategyTradesHandler,
    DeleteStrategyHandler,
    RunBacktestHandler,
    RunOptimizationHandler,
    GetBacktestHandler,
    GetOptimizationHandler,
    ListBacktestsHandler,
]
