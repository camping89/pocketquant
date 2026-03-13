"""Get strategies query handler."""


from src.application.strategy.strategy_engine import StrategyEngine
from src.common.mediator import Handler, handles
from src.features.strategy.get_all.query import GetStrategiesQuery


@handles(GetStrategiesQuery)
class GetStrategiesHandler(Handler[GetStrategiesQuery, list]):
    """Handle GetStrategiesQuery."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, request: GetStrategiesQuery) -> list:
        """Get all loaded strategies."""
        return self._engine.get_strategies()
