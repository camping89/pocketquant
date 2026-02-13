"""CQRS query for listing backtests."""

from pydantic import BaseModel


class ListBacktestsQuery(BaseModel):
    """Query to list backtest results for a strategy."""

    strategy_id: str
    limit: int = 20
    include_failed: bool = False
