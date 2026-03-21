"""Start strategy command definition."""

from pydantic import BaseModel, Field


class StartStrategyCommand(BaseModel):
    """Start a loaded strategy."""

    strategy_id: str = Field(..., description="Strategy identifier")
