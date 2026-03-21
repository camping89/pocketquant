"""Backtesting feature module - historical replay and optimization."""

from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.optimization.grid_optimization_app_service import GridOptimizationAppService
from pocketquant.backtest.engine.historical_replay_app_service import HistoricalReplayAppService
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.backtest.optimization.models.optimization_config import OptimizationConfig
from pocketquant.backtest.domain import BacktestMetrics, BacktestResult, OptimizationResult
from pocketquant.backtest.handlers.get_optimization import (
    GetOptimizationHandler,
    GetOptimizationQuery,
)
from pocketquant.backtest.handlers.get_result import (
    GetBacktestHandler,
    GetBacktestQuery,
)
from pocketquant.backtest.handlers.list_results import (
    ListBacktestsHandler,
    ListBacktestsQuery,
)
from pocketquant.backtest.handlers.optimize import (
    RunOptimizationCommand,
    RunOptimizationHandler,
)
from pocketquant.backtest.handlers.router import router as backtest_router
from pocketquant.backtest.handlers.run import (
    RunBacktestCommand,
    RunBacktestHandler,
)
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository

__all__ = [
    # Router
    "backtest_router",
    # Engine
    "BacktestAppService",
    "HistoricalReplayAppService",
    # Optimizer
    "GridOptimizationAppService",
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
