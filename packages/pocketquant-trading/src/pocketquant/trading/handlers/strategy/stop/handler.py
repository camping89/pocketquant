"""Stop strategy command handler."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.handlers.strategy.stop.command import StopStrategyCommand


@handles(StopStrategyCommand)
class StopStrategyHandler(Handler[StopStrategyCommand, bool]):
    def __init__(self, strategy_app_service: StrategyAppService) -> None:
        self._strategy_app_service = strategy_app_service

    async def handle(self, request: StopStrategyCommand) -> bool:
        await self._strategy_app_service.stop_strategy(request.subscription_id)
        return True
