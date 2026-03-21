"""List positions handler."""

from pocketquant.trading.app_services.position_app_service import PositionAppService
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.trading.list_positions.query import ListPositionsQuery


@handles(ListPositionsQuery)
class ListPositionsHandler(Handler[ListPositionsQuery, list[dict]]):
    """Handler to list all positions."""

    def __init__(self, position_tracker: PositionAppService):
        self.position_tracker = position_tracker

    async def handle(self, request: ListPositionsQuery) -> list[dict]:
        """Get all open positions."""
        return self.position_tracker.get_all_summaries()
