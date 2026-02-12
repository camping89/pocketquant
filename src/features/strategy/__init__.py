"""Strategy feature - trading strategy management and execution."""

from src.features.strategy.api import strategy_router
from src.features.strategy.base import IStrategy, OrderConfig, StrategyConfig
from src.features.strategy.engine import StrategyEngine
from src.features.strategy.examples import MACrossoverStrategy
from src.features.strategy.handlers import (
    GetStrategiesHandler,
    GetStrategiesQuery,
    GetStrategyHandler,
    GetStrategyQuery,
    LoadStrategyCommand,
    LoadStrategyHandler,
    StartStrategyCommand,
    StartStrategyHandler,
    StopStrategyCommand,
    StopStrategyHandler,
)
from src.features.strategy.loader import StrategyLoader

__all__ = [
    # Base
    "IStrategy",
    "OrderConfig",
    "StrategyConfig",
    # Engine
    "StrategyEngine",
    # Examples
    "MACrossoverStrategy",
    # Loader
    "StrategyLoader",
    # Handlers
    "GetStrategiesHandler",
    "GetStrategiesQuery",
    "GetStrategyHandler",
    "GetStrategyQuery",
    "LoadStrategyCommand",
    "LoadStrategyHandler",
    "StartStrategyCommand",
    "StartStrategyHandler",
    "StopStrategyCommand",
    "StopStrategyHandler",
    # API
    "strategy_router",
]
