"""Get position handler."""

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.execution.app_services.position_app_service import PositionAppService
from pocketquant.trading.handlers.trading.get_position.query import GetPositionQuery


@handles(GetPositionQuery)
class GetPositionHandler(Handler[GetPositionQuery, dict]):
    def __init__(self, position_app_service: PositionAppService):
        self._position_app_service = position_app_service

    async def handle(self, request: GetPositionQuery) -> dict:
        summary = self._position_app_service.get_position_summary(request.strategy_id)

        if not summary:
            raise NotFoundError(f"No position for strategy: {request.strategy_id}")

        return summary
