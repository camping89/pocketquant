"""RemoveSubscriptionCommand — delete a single subscription and its cached backtest."""

from pydantic import BaseModel


class RemoveSymbolCommand(BaseModel):
    """Command to remove a subscription by sub_id."""

    sub_id: str
