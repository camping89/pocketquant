"""Get strategies query handler."""


from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.strategy.get_all.query import GetStrategiesQuery


@handles(GetStrategiesQuery)
class GetStrategiesHandler(Handler[GetStrategiesQuery, list]):
    """Handle GetStrategiesQuery."""

    def __init__(self, strategy_app_service: StrategyAppService) -> None:
        self._strategy_app_service = strategy_app_service

    async def handle(self, request: GetStrategiesQuery) -> list:
        """Get all loaded strategies."""
        return self._strategy_app_service.get_strategies()
