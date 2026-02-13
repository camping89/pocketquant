"""Stop strategy command definition."""

from pydantic import BaseModel, Field


class StopStrategyCommand(BaseModel):
    """Stop a running strategy."""

    strategy_id: str = Field(..., description="Strategy identifier")
