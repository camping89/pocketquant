"""Auto-register all backtesting CQRS handlers with mediator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.common.mediator import HandlerRegistry, Mediator
from src.common.messaging import EventBus
from src.features.backtesting.get_optimization.handler import GetOptimizationHandler
from src.features.backtesting.get_result.handler import GetBacktestHandler
from src.features.backtesting.list_results.handler import ListBacktestsHandler
from src.features.backtesting.optimize.handler import RunOptimizationHandler
from src.features.backtesting.run.handler import RunBacktestHandler

if TYPE_CHECKING:
    from src.application.strategy.strategy_engine import StrategyEngine


def register_handlers(
    mediator: Mediator,
    event_bus: EventBus,
    strategy_engine: StrategyEngine,
) -> None:
    """Register all backtesting handlers with mediator."""
    registry = HandlerRegistry()
    registry.register_all(
        mediator,
        [
            RunBacktestHandler(event_bus, strategy_engine),
            RunOptimizationHandler(event_bus, strategy_engine),
            GetBacktestHandler(),
            GetOptimizationHandler(),
            ListBacktestsHandler(),
        ],
    )
