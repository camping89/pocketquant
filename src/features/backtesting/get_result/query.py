"""CQRS query for getting backtest result."""

from pydantic import BaseModel


class GetBacktestQuery(BaseModel):
    """Query to get a specific backtest result by ID."""

    run_id: str
