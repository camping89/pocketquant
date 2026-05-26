"""List strategy templates from STRATEGY_REGISTRY."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
from pocketquant.trading.handlers.strategy.get_all.query import GetStrategiesQuery


@handles(GetStrategiesQuery)
class GetStrategiesHandler(Handler[GetStrategiesQuery, list]):
    """Handle GetStrategiesQuery — list registered strategy templates."""

    async def handle(self, request: GetStrategiesQuery) -> list:
        """Return one entry per registered template in STRATEGY_REGISTRY."""
        return [{"strategy_code": code} for code in STRATEGY_REGISTRY.keys()]
