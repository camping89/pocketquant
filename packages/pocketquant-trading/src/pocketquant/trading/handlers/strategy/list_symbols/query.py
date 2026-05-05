"""ListSymbolsQuery — retrieve all subscriptions for a strategy with backtest status."""

from pydantic import BaseModel


class ListSymbolsQuery(BaseModel):
    """Query to list all symbol subscriptions for a given strategy."""

    strategy_id: str
