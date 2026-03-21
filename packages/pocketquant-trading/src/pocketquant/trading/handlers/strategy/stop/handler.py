"""Stop strategy command handler."""


from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.strategy.stop.command import StopStrategyCommand


@handles(StopStrategyCommand)
class StopStrategyHandler(Handler[StopStrategyCommand, bool]):
    """Handle StopStrategyCommand."""

    def __init__(self, engine: StrategyAppService) -> None:
        self._engine = engine

    async def handle(self, request: StopStrategyCommand) -> bool:
        """Stop a running strategy."""
        await self._engine.stop_strategy(request.strategy_id)
        return True
