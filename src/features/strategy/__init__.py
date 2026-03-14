"""Strategy feature - trading strategy management and execution."""

from src.application.strategy.strategy_app_service import StrategyAppService
from src.application.strategy.yaml_strategy_loader import StrategyLoader
from src.domain.strategy.interfaces import IStrategy
from src.domain.strategy.strategies.ma_crossover import MACrossoverStrategy
from src.domain.strategy.value_objects import OrderConfig, StrategyConfig
from src.features.strategy.get_all import GetStrategiesHandler, GetStrategiesQuery
from src.features.strategy.get_one import GetStrategyHandler, GetStrategyQuery
from src.features.strategy.load import LoadStrategyCommand, LoadStrategyHandler
from src.features.strategy.router import router as strategy_router
from src.features.strategy.start import StartStrategyCommand, StartStrategyHandler
from src.features.strategy.stop import StopStrategyCommand, StopStrategyHandler

__all__ = [
    # Base
    "IStrategy",
    "OrderConfig",
    "StrategyConfig",
    # Engine
    "StrategyAppService",
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
