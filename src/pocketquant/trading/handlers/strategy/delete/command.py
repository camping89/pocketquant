"""DeleteStrategyCommand — cascade unload and delete all strategy data."""

from pydantic import BaseModel


class DeleteStrategyCommand(BaseModel):
    """Command to fully delete a strategy: unload, cancel jobs, wipe subs + backtests."""

    strategy_id: str
