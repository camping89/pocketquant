"""Stop strategy command handler."""

from typing import TYPE_CHECKING

from src.common.mediator import Handler, handles
from src.features.strategy.stop.command import StopStrategyCommand

if TYPE_CHECKING:
    from src.application.strategy.strategy_engine import StrategyEngine


@handles(StopStrategyCommand)
class StopStrategyHandler(Handler[StopStrategyCommand, bool]):
    """Handle StopStrategyCommand."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, request: StopStrategyCommand) -> bool:
        """Stop a running strategy."""
        await self._engine.stop_strategy(request.strategy_id)
        return True
