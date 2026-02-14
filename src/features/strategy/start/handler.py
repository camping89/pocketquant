"""Start strategy command handler."""

from typing import TYPE_CHECKING

from src.common.mediator import Handler, handles
from src.features.strategy.start.command import StartStrategyCommand

if TYPE_CHECKING:
    from src.features.strategy.base import StrategyEngine


@handles(StartStrategyCommand)
class StartStrategyHandler(Handler[StartStrategyCommand, bool]):
    """Handle StartStrategyCommand."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, request: StartStrategyCommand) -> bool:
        """Start a loaded strategy."""
        await self._engine.start_strategy(request.strategy_id)
        return True
