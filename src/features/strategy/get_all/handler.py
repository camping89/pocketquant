"""Get strategies query handler."""

from typing import TYPE_CHECKING

from src.common.mediator import Handler
from src.features.strategy.get_all.query import GetStrategiesQuery

if TYPE_CHECKING:
    from src.features.strategy.base import StrategyEngine


class GetStrategiesHandler(Handler[GetStrategiesQuery, list]):
    """Handle GetStrategiesQuery."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, request: GetStrategiesQuery) -> list:
        """Get all loaded strategies."""
        return self._engine.get_strategies()
