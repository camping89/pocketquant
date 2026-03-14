"""Start strategy command handler."""


from src.application.strategy.strategy_app_service import StrategyAppService
from src.common.mediator import Handler, handles
from src.features.strategy.start.command import StartStrategyCommand


@handles(StartStrategyCommand)
class StartStrategyHandler(Handler[StartStrategyCommand, bool]):
    """Handle StartStrategyCommand."""

    def __init__(self, engine: StrategyAppService) -> None:
        self._engine = engine

    async def handle(self, request: StartStrategyCommand) -> bool:
        """Start a loaded strategy."""
        await self._engine.start_strategy(request.strategy_id)
        return True
