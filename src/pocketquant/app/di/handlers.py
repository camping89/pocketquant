"""CQRS handler providers for app — only backtest handlers remain via Mediator.

App is headless (no HTTP). Background jobs call SyncService directly — no
Mediator dispatch for market-data paths. Trading/strategy handlers are removed:
those routes now call feature services directly. Backtest handlers are kept
because the backtest worker still dispatches them via Mediator.
"""

from dishka import Provider, Scope, provide

from pocketquant.backtest.handlers.get_optimization.handler import GetOptimizationHandler
from pocketquant.backtest.handlers.get_result.handler import GetBacktestHandler
from pocketquant.backtest.handlers.list_results.handler import ListBacktestsHandler
from pocketquant.backtest.handlers.optimize.handler import RunOptimizationHandler
from pocketquant.backtest.handlers.run.handler import RunBacktestHandler
from pocketquant.backtest.handlers.run_all_backtests.handler import RunAllBacktestsHandler


class HandlerProvider(Provider):
    # Backtest — worker dispatches these via Mediator
    run_all_backtests_handler = provide(RunAllBacktestsHandler, scope=Scope.APP)
    run_backtest_handler = provide(RunBacktestHandler, scope=Scope.APP)
    run_optimization_handler = provide(RunOptimizationHandler, scope=Scope.APP)
    get_backtest_handler = provide(GetBacktestHandler, scope=Scope.APP)
    get_optimization_handler = provide(GetOptimizationHandler, scope=Scope.APP)
    list_backtests_handler = provide(ListBacktestsHandler, scope=Scope.APP)


ALL_HANDLER_TYPES: list[type] = [
    RunAllBacktestsHandler,
    RunBacktestHandler,
    RunOptimizationHandler,
    GetBacktestHandler,
    GetOptimizationHandler,
    ListBacktestsHandler,
]
