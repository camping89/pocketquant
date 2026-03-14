"""Get strategies query handler."""


from src.application.strategy.strategy_app_service import StrategyAppService
from src.common.mediator import Handler, handles
from src.features.strategy.get_all.query import GetStrategiesQuery


@handles(GetStrategiesQuery)
class GetStrategiesHandler(Handler[GetStrategiesQuery, list]):
    """Handle GetStrategiesQuery."""

    def __init__(self, engine: StrategyAppService) -> None:
        self._engine = engine

    async def handle(self, request: GetStrategiesQuery) -> list:
        """Get all loaded strategies."""
        return self._engine.get_strategies()
