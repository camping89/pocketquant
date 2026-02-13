"""List positions handler."""

from src.common.mediator import Handler
from src.features.trading.base.managers.position_tracker import PositionTracker
from src.features.trading.list_positions.query import ListPositionsQuery


class ListPositionsHandler(Handler[ListPositionsQuery, list[dict]]):
    """Handler to list all positions."""

    def __init__(self, position_tracker: PositionTracker):
        self.position_tracker = position_tracker

    async def handle(self, request: ListPositionsQuery) -> list[dict]:
        """Get all open positions."""
        return self.position_tracker.get_all_summaries()
