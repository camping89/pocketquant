"""List positions handler."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.engine.app_services.position_app_service import PositionAppService
from pocketquant.trading.handlers.trading.list_positions.query import ListPositionsQuery


@handles(ListPositionsQuery)
class ListPositionsHandler(Handler[ListPositionsQuery, list[dict]]):
    def __init__(self, position_app_service: PositionAppService):
        self._position_app_service = position_app_service

    async def handle(self, request: ListPositionsQuery) -> list[dict]:
        return self._position_app_service.get_all_summaries()
