"""Stop strategy command handler."""


from src.application.strategy.strategy_app_service import StrategyAppService
from src.common.mediator import Handler, handles
from src.features.strategy.stop.command import StopStrategyCommand


@handles(StopStrategyCommand)
class StopStrategyHandler(Handler[StopStrategyCommand, bool]):
    """Handle StopStrategyCommand."""

    def __init__(self, engine: StrategyAppService) -> None:
        self._engine = engine

    async def handle(self, request: StopStrategyCommand) -> bool:
        """Stop a running strategy."""
        await self._engine.stop_strategy(request.strategy_id)
        return True
