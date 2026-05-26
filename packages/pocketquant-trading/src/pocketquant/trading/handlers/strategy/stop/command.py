"""Stop subscription command definition."""

from pydantic import BaseModel, Field


class StopStrategyCommand(BaseModel):
    """Stop the strategy instance for a subscription."""

    subscription_id: str = Field(..., description="Deterministic subscription identifier")
