"""Strategy command handlers."""

from src.common.mediator import Handler
from src.features.strategy.engine import StrategyEngine
from src.features.strategy.handlers.commands import (
    LoadStrategyCommand,
    StartStrategyCommand,
    StopStrategyCommand,
)
from src.features.strategy.loader import StrategyLoader


class LoadStrategyHandler(Handler[LoadStrategyCommand, str]):
    """Handle LoadStrategyCommand."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, request: LoadStrategyCommand) -> str:
        """Load strategy from config or path."""
        if request.config:
            config = request.config
        elif request.path:
            config = StrategyLoader.load(request.path)
        else:
            raise ValueError("Either config or path must be provided")

        return await self._engine.load_strategy(config)


class StartStrategyHandler(Handler[StartStrategyCommand, bool]):
    """Handle StartStrategyCommand."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, request: StartStrategyCommand) -> bool:
        """Start a loaded strategy."""
        await self._engine.start_strategy(request.strategy_id)
        return True


class StopStrategyHandler(Handler[StopStrategyCommand, bool]):
    """Handle StopStrategyCommand."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, request: StopStrategyCommand) -> bool:
        """Stop a running strategy."""
        await self._engine.stop_strategy(request.strategy_id)
        return True
