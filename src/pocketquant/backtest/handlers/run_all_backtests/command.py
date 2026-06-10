"""RunAllBacktestsCommand — fan-out one-off backtest jobs for all subscriptions."""

from pydantic import BaseModel


class RunAllBacktestsCommand(BaseModel):
    """Command to enqueue a backtest job for every subscription of a strategy."""

    strategy_id: str
