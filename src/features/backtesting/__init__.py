"""Backtesting feature module - historical replay and optimization."""

from src.features.backtesting.base import (
    BacktestConfig,
    BacktestMetrics,
    BacktestRepository,
    BacktestResult,
    BacktestRunner,
    GridOptimizer,
    HistoricalReplayEngine,
    OptimizationConfig,
    OptimizationResult,
)
from src.features.backtesting.get_optimization import (
    GetOptimizationHandler,
    GetOptimizationQuery,
)
from src.features.backtesting.get_result import (
    GetBacktestHandler,
    GetBacktestQuery,
)
from src.features.backtesting.list_results import (
    ListBacktestsHandler,
    ListBacktestsQuery,
)
from src.features.backtesting.optimize import (
    RunOptimizationCommand,
    RunOptimizationHandler,
)
from src.features.backtesting.router import router as backtest_router
from src.features.backtesting.run import (
    RunBacktestCommand,
    RunBacktestHandler,
)

__all__ = [
    # Router
    "backtest_router",
    # Engine
    "BacktestRunner",
    "HistoricalReplayEngine",
    # Optimizer
    "GridOptimizer",
    # Models
    "BacktestConfig",
    "BacktestResult",
    "BacktestMetrics",
    "OptimizationConfig",
    "OptimizationResult",
    # Repository
    "BacktestRepository",
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
