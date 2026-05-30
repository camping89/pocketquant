"""Start strategy command handler."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.handlers.strategy.start.command import StartStrategyCommand


@handles(StartStrategyCommand)
class StartStrategyHandler(Handler[StartStrategyCommand, bool]):
    def __init__(self, strategy_app_service: StrategyAppService) -> None:
        self._strategy_app_service = strategy_app_service

    async def handle(self, request: StartStrategyCommand) -> bool:
        await self._strategy_app_service.start_strategy(request.subscription_id)
        return True
