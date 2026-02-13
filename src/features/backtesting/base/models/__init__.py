"""Backtest models submodule - configuration and result dataclasses."""

from src.features.backtesting.base.models.backtest_config import BacktestConfig
from src.features.backtesting.base.models.backtest_result import (
    BacktestMetrics,
    BacktestResult,
    EquityPoint,
    TradeRecord,
)
from src.features.backtesting.base.models.optimization_config import OptimizationConfig
from src.features.backtesting.base.models.optimization_result import (
    OptimizationResult,
    OptimizationResultEntry,
)

__all__ = [
    "BacktestConfig",
    "BacktestMetrics",
    "BacktestResult",
    "EquityPoint",
    "TradeRecord",
    "OptimizationConfig",
    "OptimizationResult",
    "OptimizationResultEntry",
]
