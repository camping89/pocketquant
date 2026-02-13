"""Get position query."""

from pydantic import BaseModel


class GetPositionQuery(BaseModel):
    """Query to get a specific position."""

    strategy_id: str
