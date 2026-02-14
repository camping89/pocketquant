"""Get strategy query handler."""

from typing import TYPE_CHECKING

from src.common.mediator import Handler, handles
from src.features.strategy.get_one.query import GetStrategyQuery

if TYPE_CHECKING:
    from src.application.strategy.strategy_engine import StrategyEngine


@handles(GetStrategyQuery)
class GetStrategyHandler(Handler[GetStrategyQuery, dict | None]):
    """Handle GetStrategyQuery."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, request: GetStrategyQuery) -> dict | None:
        """Get a specific strategy by ID."""
        strategy = self._engine.get_strategy(request.strategy_id)
        if not strategy:
            return None

        return {
            "id": strategy.id,
            "name": strategy.config.name,
            "symbol": strategy.config.symbol,
            "exchange": strategy.config.exchange,
            "interval": strategy.config.interval,
            "broker": strategy.config.broker,
            "is_running": strategy.is_running,
            "parameters": strategy.config.parameters,
        }
