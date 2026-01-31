"""Backtest handlers submodule - CQRS command and query handlers."""

from src.features.backtesting.handlers.backtest_commands import (
    GetBacktestQuery,
    GetOptimizationQuery,
    ListBacktestsQuery,
    RunBacktestCommand,
    RunOptimizationCommand,
)
from src.features.backtesting.handlers.backtest_handlers import (
    GetBacktestHandler,
    GetOptimizationHandler,
    ListBacktestsHandler,
    RunBacktestHandler,
    RunOptimizationHandler,
)

__all__ = [
    # Commands/Queries
    "RunBacktestCommand",
    "RunOptimizationCommand",
    "GetBacktestQuery",
    "GetOptimizationQuery",
    "ListBacktestsQuery",
    # Handlers
    "RunBacktestHandler",
    "RunOptimizationHandler",
    "GetBacktestHandler",
    "GetOptimizationHandler",
    "ListBacktestsHandler",
]
