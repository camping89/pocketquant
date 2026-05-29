"""Strategy feature - trading strategy management and execution."""

from pocketquant.core.concepts.strategy.interfaces import IStrategy
from pocketquant.core.concepts.strategy.value_objects import OrderConfig, StrategyConfig
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.handlers.strategy.get_all import GetStrategiesHandler, GetStrategiesQuery
from pocketquant.trading.handlers.strategy.get_one import GetStrategyHandler, GetStrategyQuery
from pocketquant.trading.handlers.strategy.router import (
    router as strategy_router,
)
from pocketquant.trading.handlers.strategy.router import (
    subscription_router,
)
from pocketquant.trading.handlers.strategy.start import StartStrategyCommand, StartStrategyHandler
from pocketquant.trading.handlers.strategy.stop import StopStrategyCommand, StopStrategyHandler

__all__ = [
    # Base
    "IStrategy",
    "OrderConfig",
    "StrategyConfig",
    # Engine
    "StrategyAppService",
    # Handlers
    "GetStrategiesHandler",
    "GetStrategiesQuery",
    "GetStrategyHandler",
    "GetStrategyQuery",
    "StartStrategyCommand",
    "StartStrategyHandler",
    "StopStrategyCommand",
    "StopStrategyHandler",
    # API
    "strategy_router",
    "subscription_router",
]
