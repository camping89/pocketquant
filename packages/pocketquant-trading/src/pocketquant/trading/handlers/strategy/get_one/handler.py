"""Get strategy query handler."""


from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.strategy.get_one.query import GetStrategyQuery


@handles(GetStrategyQuery)
class GetStrategyHandler(Handler[GetStrategyQuery, dict | None]):
    """Handle GetStrategyQuery."""

    def __init__(self, strategy_app_service: StrategyAppService) -> None:
        self._strategy_app_service = strategy_app_service

    async def handle(self, request: GetStrategyQuery) -> dict | None:
        """Get a specific strategy by ID."""
        strategy = self._strategy_app_service.get_strategy(request.strategy_id)
        if not strategy:
            return None

        return {
            "id": strategy.id,
            "name": strategy.config.name,
            "symbol": strategy.config.symbol,
            "exchange": strategy.config.exchange,
            "interval": strategy.config.interval,
            "broker": strategy.config.broker,
            "is_running": strategy.is_running,
            "parameters": strategy.config.parameters,
        }
