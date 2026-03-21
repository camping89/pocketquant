"""Get strategies query handler."""


from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.strategy.get_all.query import GetStrategiesQuery


@handles(GetStrategiesQuery)
class GetStrategiesHandler(Handler[GetStrategiesQuery, list]):
    """Handle GetStrategiesQuery."""

    def __init__(self, engine: StrategyAppService) -> None:
        self._engine = engine

    async def handle(self, request: GetStrategiesQuery) -> list:
        """Get all loaded strategies."""
        return self._engine.get_strategies()
