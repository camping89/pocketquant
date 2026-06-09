"""CQRS handler provider for bff — all handlers bff serves via Mediator.

Excludes the 5 dropped live-runtime quote handlers (get_all, get_status/subscribe-count,
subscribe, unsubscribe, get_quote_service_status) and any engine/scheduler-only
handlers (none exist here — all bff handlers are pure Mongo/Cache reads/writes).
"""

from dishka import Provider, Scope, provide
from pocketquant.backtest.handlers.get_optimization.handler import GetOptimizationHandler
from pocketquant.backtest.handlers.get_result.handler import GetBacktestHandler
from pocketquant.backtest.handlers.list_results.handler import ListBacktestsHandler
from pocketquant.backtest.handlers.optimize.handler import RunOptimizationHandler
from pocketquant.backtest.handlers.run.handler import RunBacktestHandler
from pocketquant.backtest.handlers.run_all_backtests.handler import RunAllBacktestsHandler
from pocketquant.execution.market_data.handlers.list_symbols.handler import ListSymbolsHandler
from pocketquant.execution.market_data.handlers.ohlcv.get_ohlcv.handler import GetOHLCVHandler
from pocketquant.execution.market_data.handlers.quotes.get_latest.handler import (
    GetLatestQuoteHandler,
)
from pocketquant.execution.market_data.handlers.status.get_symbol_sync_status.handler import (
    GetSymbolSyncStatusHandler,
)
from pocketquant.execution.market_data.handlers.status.get_sync_status.handler import (
    GetSyncStatusHandler,
)
from pocketquant.execution.market_data.handlers.sync.sync_bulk.handler import BulkSyncHandler
from pocketquant.execution.market_data.handlers.sync.sync_one.handler import SyncSymbolHandler
from pocketquant.execution.market_data.handlers.tracked_symbols.add.handler import (
    AddTrackedSymbolHandler,
)
from pocketquant.execution.market_data.handlers.tracked_symbols.backfill.handler import (
    BackfillTrackedSymbolHandler,
)
from pocketquant.execution.market_data.handlers.tracked_symbols.list_all.handler import (
    ListTrackedSymbolsHandler,
)
from pocketquant.execution.market_data.handlers.tracked_symbols.remove.handler import (
    RemoveTrackedSymbolHandler,
)
from pocketquant.execution.market_data.handlers.tracked_symbols.update.handler import (
    UpdateTrackedSymbolHandler,
)
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
from pocketquant.trading.handlers.strategy.get_trades.handler import GetStrategyTradesHandler
from pocketquant.trading.handlers.strategy.list_symbols.handler import (
    ListSymbolsHandler as ListStrategySymbolsHandler,
)
from pocketquant.trading.handlers.strategy.remove_symbol.handler import RemoveSymbolHandler
from pocketquant.trading.handlers.strategy.start.handler import StartStrategyHandler
from pocketquant.trading.handlers.strategy.stop.handler import StopStrategyHandler

# NOTE: GetOrderHandler, GetPositionHandler, ListOrdersHandler, ListPositionsHandler
# require OrderAppService / PositionAppService (in-RAM live engine state). These
# cannot be served correctly from the stateless bff — they are excluded.


class BffHandlerProvider(Provider):
    # Market data — execution package
    list_tracked_symbols_handler = provide(ListTrackedSymbolsHandler, scope=Scope.APP)
    add_tracked_symbol_handler = provide(AddTrackedSymbolHandler, scope=Scope.APP)
    update_tracked_symbol_handler = provide(UpdateTrackedSymbolHandler, scope=Scope.APP)
    remove_tracked_symbol_handler = provide(RemoveTrackedSymbolHandler, scope=Scope.APP)
    sync_symbol_handler = provide(SyncSymbolHandler, scope=Scope.APP)
    bulk_sync_handler = provide(BulkSyncHandler, scope=Scope.APP)
    get_ohlcv_handler = provide(GetOHLCVHandler, scope=Scope.APP)
    get_latest_quote_handler = provide(GetLatestQuoteHandler, scope=Scope.APP)
    get_sync_status_handler = provide(GetSyncStatusHandler, scope=Scope.APP)
    get_symbol_sync_status_handler = provide(GetSymbolSyncStatusHandler, scope=Scope.APP)
    list_symbols_handler = provide(ListSymbolsHandler, scope=Scope.APP)
    # BackfillTrackedSymbolHandler is NOT a Mediator handler (no @handles) — route
    # instantiates it directly via DI. Provide it so dishka can inject into route.
    backfill_tracked_symbol_handler = provide(BackfillTrackedSymbolHandler, scope=Scope.APP)

    # Trading — pure Mongo writes/reads (declarative after Phase 3)
    # list_orders / get_order / list_positions / get_position excluded: they depend
    # on OrderAppService / PositionAppService which hold live in-RAM engine state.
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

    # Backtest — enqueue-only (pure DB write, no engine)
    run_backtest_handler = provide(RunBacktestHandler, scope=Scope.APP)
    run_optimization_handler = provide(RunOptimizationHandler, scope=Scope.APP)
    get_backtest_handler = provide(GetBacktestHandler, scope=Scope.APP)
    get_optimization_handler = provide(GetOptimizationHandler, scope=Scope.APP)
    list_backtests_handler = provide(ListBacktestsHandler, scope=Scope.APP)


ALL_BFF_HANDLER_TYPES: list[type] = [
    ListTrackedSymbolsHandler,
    AddTrackedSymbolHandler,
    UpdateTrackedSymbolHandler,
    RemoveTrackedSymbolHandler,
    SyncSymbolHandler,
    BulkSyncHandler,
    GetOHLCVHandler,
    GetLatestQuoteHandler,
    GetSyncStatusHandler,
    GetSymbolSyncStatusHandler,
    ListSymbolsHandler,
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
