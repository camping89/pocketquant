"""GetSubscriptionBacktestQuery — fetch cached backtest result for a subscription."""

from pydantic import BaseModel


class GetSubscriptionBacktestQuery(BaseModel):
    """Query to retrieve the full backtest doc for a single subscription."""

    strategy_id: str
    sub_id: str
