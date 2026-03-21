"""Start strategy command handler."""


from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.strategy.start.command import StartStrategyCommand


@handles(StartStrategyCommand)
class StartStrategyHandler(Handler[StartStrategyCommand, bool]):
    """Handle StartStrategyCommand."""

    def __init__(self, engine: StrategyAppService) -> None:
        self._engine = engine

    async def handle(self, request: StartStrategyCommand) -> bool:
        """Start a loaded strategy."""
        await self._engine.start_strategy(request.strategy_id)
        return True
