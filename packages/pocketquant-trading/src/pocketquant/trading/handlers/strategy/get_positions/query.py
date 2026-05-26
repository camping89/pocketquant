"""Query: list open positions for a subscription instance."""

from pydantic import BaseModel


class GetStrategyPositionsQuery(BaseModel):
    """Read-side query — returns open positions for ``subscription_id``."""

    subscription_id: str
