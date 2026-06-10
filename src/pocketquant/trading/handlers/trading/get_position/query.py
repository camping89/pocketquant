"""Get position query."""

from pydantic import BaseModel


class GetPositionQuery(BaseModel):
    strategy_id: str
