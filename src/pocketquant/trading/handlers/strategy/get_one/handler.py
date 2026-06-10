"""Get strategy template metadata handler."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.trading.handlers.strategy.get_one.query import GetStrategyQuery


@handles(GetStrategyQuery)
class GetStrategyHandler(Handler[GetStrategyQuery, dict | None]):
    """Handle GetStrategyQuery — return template metadata for a strategy code."""

    async def handle(self, request: GetStrategyQuery) -> dict | None:
        strategy_class = STRATEGY_REGISTRY.get(request.strategy_code)
        if strategy_class is None:
            return None
        return {
            "strategy_code": request.strategy_code,
            "class_name": strategy_class.__name__,
            "description": (strategy_class.__doc__ or "").strip().split("\n")[0]
            if strategy_class.__doc__
            else "",
        }
