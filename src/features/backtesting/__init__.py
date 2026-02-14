"""Backtesting feature module - historical replay and optimization."""

from src.application.backtesting.backtest_runner import BacktestRunner
from src.application.backtesting.grid_optimizer import GridOptimizer
from src.application.backtesting.historical_replay_engine import HistoricalReplayEngine
from src.application.backtesting.models.backtest_config import BacktestConfig
from src.application.backtesting.models.backtest_result import BacktestMetrics, BacktestResult
from src.application.backtesting.models.optimization_config import OptimizationConfig
from src.application.backtesting.models.optimization_result import OptimizationResult
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
from src.persistence.repositories.backtest_repository import BacktestRepository

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
