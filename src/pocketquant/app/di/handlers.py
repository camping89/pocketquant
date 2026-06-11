"""CQRS handler providers for app — all handlers resolved from execution/backtest/trading.

App is headless (no HTTP). Background jobs (sync_jobs, integrity_jobs) now call
SyncService directly — no Mediator dispatch for market-data paths. All other
handlers are kept so that the DI graph resolves cleanly.
HTTP-only quote handlers (get_all, get_status/subscribe-count, subscribe,
unsubscribe, get_quote_service_status) are excluded — they were removed when
bff took over routes.
"""

from dishka import Provider, Scope, provide

from pocketquant.backtest.handlers.get_optimization.handler import GetOptimizationHandler
from pocketquant.backtest.handlers.get_result.handler import GetBacktestHandler
from pocketquant.backtest.handlers.list_results.handler import ListBacktestsHandler
from pocketquant.backtest.handlers.optimize.handler import RunOptimizationHandler
from pocketquant.backtest.handlers.run.handler import RunBacktestHandler
from pocketquant.backtest.handlers.run_all_backtests.handler import RunAllBacktestsHandler
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
from pocketquant.trading.handlers.trading.get_order.handler import GetOrderHandler
from pocketquant.trading.handlers.trading.get_position.handler import GetPositionHandler
from pocketquant.trading.handlers.trading.list_orders.handler import ListOrdersHandler
from pocketquant.trading.handlers.trading.list_positions.handler import ListPositionsHandler


class HandlerProvider(Provider):
    list_orders_handler = provide(ListOrdersHandler, scope=Scope.APP)
    get_order_handler = provide(GetOrderHandler, scope=Scope.APP)
    list_positions_handler = provide(ListPositionsHandler, scope=Scope.APP)
    get_position_handler = provide(GetPositionHandler, scope=Scope.APP)

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

    run_backtest_handler = provide(RunBacktestHandler, scope=Scope.APP)
    run_optimization_handler = provide(RunOptimizationHandler, scope=Scope.APP)
    get_backtest_handler = provide(GetBacktestHandler, scope=Scope.APP)
    get_optimization_handler = provide(GetOptimizationHandler, scope=Scope.APP)
    list_backtests_handler = provide(ListBacktestsHandler, scope=Scope.APP)


ALL_HANDLER_TYPES: list[type] = [
    ListOrdersHandler,
    GetOrderHandler,
    ListPositionsHandler,
    GetPositionHandler,
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
