"""Backtesting infrastructure - engine, metrics, optimizer, repository, models."""

from src.features.backtesting.base.engine import (
    BacktestRunner,
    HistoricalReplayEngine,
    ReplayStats,
)
from src.features.backtesting.base.metrics import (
    BacktestResultCollector,
    PerformanceCalculator,
)
from src.features.backtesting.base.models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    EquityPoint,
    OptimizationConfig,
    OptimizationResult,
    OptimizationResultEntry,
    TradeRecord,
)
from src.features.backtesting.base.optimizer import GridOptimizer
from src.features.backtesting.base.repository import BacktestRepository

__all__ = [
    # Engine
    "BacktestRunner",
    "HistoricalReplayEngine",
    "ReplayStats",
    # Metrics
    "BacktestResultCollector",
    "PerformanceCalculator",
    # Models
    "BacktestConfig",
    "BacktestMetrics",
    "BacktestResult",
    "EquityPoint",
    "TradeRecord",
    "OptimizationConfig",
    "OptimizationResult",
    "OptimizationResultEntry",
    # Optimizer
    "GridOptimizer",
    # Repository
    "BacktestRepository",
]
