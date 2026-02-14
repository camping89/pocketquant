"""Get position handler."""

from fastapi import HTTPException

from src.application.trading.position_tracker import PositionTracker
from src.common.mediator import Handler, handles
from src.features.trading.get_position.query import GetPositionQuery


@handles(GetPositionQuery)
class GetPositionHandler(Handler[GetPositionQuery, dict]):
    """Handler to get a specific position."""

    def __init__(self, position_tracker: PositionTracker):
        self.position_tracker = position_tracker

    async def handle(self, request: GetPositionQuery) -> dict:
        """Get position for a specific strategy."""
        summary = self.position_tracker.get_position_summary(request.strategy_id)

        if not summary:
            raise HTTPException(
                status_code=404,
                detail=f"No position for strategy: {request.strategy_id}",
            )

        return summary
