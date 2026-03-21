"""Strategy feature - trading strategy management and execution."""

from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.app_services.yaml_strategy_loader import StrategyLoader
from pocketquant.core.concepts.strategy.interfaces import IStrategy
from pocketquant.core.concepts.strategy.services.ma_crossover import MACrossoverStrategy
from pocketquant.core.concepts.strategy.value_objects import OrderConfig, StrategyConfig
from pocketquant.trading.handlers.strategy.get_all import GetStrategiesHandler, GetStrategiesQuery
from pocketquant.trading.handlers.strategy.get_one import GetStrategyHandler, GetStrategyQuery
from pocketquant.trading.handlers.strategy.load import LoadStrategyCommand, LoadStrategyHandler
from pocketquant.trading.handlers.strategy.router import router as strategy_router
from pocketquant.trading.handlers.strategy.start import StartStrategyCommand, StartStrategyHandler
from pocketquant.trading.handlers.strategy.stop import StopStrategyCommand, StopStrategyHandler

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
