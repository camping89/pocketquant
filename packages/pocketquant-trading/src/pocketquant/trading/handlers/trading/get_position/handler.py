"""Get position handler."""

from pocketquant.trading.app_services.position_app_service import PositionAppService
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.trading.get_position.query import GetPositionQuery


@handles(GetPositionQuery)
class GetPositionHandler(Handler[GetPositionQuery, dict]):
    """Handler to get a specific position."""

    def __init__(self, position_tracker: PositionAppService):
        self.position_tracker = position_tracker

    async def handle(self, request: GetPositionQuery) -> dict:
        """Get position for a specific strategy."""
        summary = self.position_tracker.get_position_summary(request.strategy_id)

        if not summary:
            raise NotFoundError(f"No position for strategy: {request.strategy_id}")

        return summary
