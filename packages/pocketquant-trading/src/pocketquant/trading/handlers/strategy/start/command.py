"""Start subscription command definition."""

from pydantic import BaseModel, Field


class StartStrategyCommand(BaseModel):
    """Start the strategy instance for a subscription."""

    subscription_id: str = Field(..., description="Deterministic subscription identifier")
