"""Load strategy command handler."""


from src.application.strategy.strategy_engine import StrategyEngine
from src.application.strategy.yaml_strategy_loader import StrategyLoader
from src.common.mediator import Handler, handles
from src.features.strategy.load.command import LoadStrategyCommand


@handles(LoadStrategyCommand)
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
