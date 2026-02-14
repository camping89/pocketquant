"""Auto-register all strategy CQRS handlers with mediator."""

from src.application.strategy.strategy_engine import StrategyEngine
from src.common.mediator import HandlerRegistry, Mediator
from src.features.strategy.get_all.handler import GetStrategiesHandler
from src.features.strategy.get_one.handler import GetStrategyHandler
from src.features.strategy.load.handler import LoadStrategyHandler
from src.features.strategy.start.handler import StartStrategyHandler
from src.features.strategy.stop.handler import StopStrategyHandler


def register_handlers(
    mediator: Mediator,
    strategy_engine: StrategyEngine,
) -> None:
    """Register all strategy handlers with mediator."""
    registry = HandlerRegistry()
    registry.register_all(
        mediator,
        [
            LoadStrategyHandler(strategy_engine),
            StartStrategyHandler(strategy_engine),
            StopStrategyHandler(strategy_engine),
            GetStrategiesHandler(strategy_engine),
            GetStrategyHandler(strategy_engine),
        ],
    )
