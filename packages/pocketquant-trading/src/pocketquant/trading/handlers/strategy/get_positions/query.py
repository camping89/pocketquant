"""Query: list open positions for a strategy/subscription instance id."""

from pydantic import BaseModel


class GetStrategyPositionsQuery(BaseModel):
    """Read-side query — returns open positions tied to ``strategy_id``.

    For the per-subscription model, ``strategy_id`` is the subscription's
    deterministic id; for legacy YAML-loaded strategies it is the YAML id.
    """

    strategy_id: str
