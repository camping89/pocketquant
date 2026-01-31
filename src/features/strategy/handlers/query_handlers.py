"""Strategy query handlers."""

from src.common.mediator import Handler
from src.features.strategy.engine import StrategyEngine
from src.features.strategy.handlers.queries import GetStrategiesQuery, GetStrategyQuery


class GetStrategiesHandler(Handler[GetStrategiesQuery, list]):
    """Handle GetStrategiesQuery."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, query: GetStrategiesQuery) -> list:
        """Get all loaded strategies."""
        return self._engine.get_strategies()


class GetStrategyHandler(Handler[GetStrategyQuery, dict | None]):
    """Handle GetStrategyQuery."""

    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine

    async def handle(self, query: GetStrategyQuery) -> dict | None:
        """Get a specific strategy by ID."""
        strategy = self._engine.get_strategy(query.strategy_id)
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
