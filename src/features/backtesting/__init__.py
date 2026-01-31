"""Backtesting feature module - historical replay and optimization."""

from src.features.backtesting.api.backtest_routes import router as backtest_router
from src.features.backtesting.engine.backtest_runner import BacktestRunner
from src.features.backtesting.engine.historical_replay_engine import HistoricalReplayEngine
from src.features.backtesting.handlers import (
    GetBacktestHandler,
    GetBacktestQuery,
    GetOptimizationHandler,
    GetOptimizationQuery,
    ListBacktestsHandler,
    ListBacktestsQuery,
    RunBacktestCommand,
    RunBacktestHandler,
    RunOptimizationCommand,
    RunOptimizationHandler,
)
from src.features.backtesting.models.backtest_config import BacktestConfig
from src.features.backtesting.models.backtest_result import BacktestMetrics, BacktestResult
from src.features.backtesting.models.optimization_config import OptimizationConfig
from src.features.backtesting.models.optimization_result import OptimizationResult
from src.features.backtesting.optimizer.grid_optimizer import GridOptimizer
from src.features.backtesting.repository.backtest_repository import BacktestRepository

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
