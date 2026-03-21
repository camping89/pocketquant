"""Load strategy command handler."""


from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.app_services.yaml_strategy_loader import StrategyLoader
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.strategy.load.command import LoadStrategyCommand


@handles(LoadStrategyCommand)
class LoadStrategyHandler(Handler[LoadStrategyCommand, str]):
    """Handle LoadStrategyCommand."""

    def __init__(self, strategy_app_service: StrategyAppService) -> None:
        self._strategy_app_service = strategy_app_service

    async def handle(self, request: LoadStrategyCommand) -> str:
        """Load strategy from config or path."""
        if request.config:
            config = request.config
        elif request.path:
            config = StrategyLoader.load(request.path)
        else:
            raise ValueError("Either config or path must be provided")

        return await self._strategy_app_service.load_strategy(config)
