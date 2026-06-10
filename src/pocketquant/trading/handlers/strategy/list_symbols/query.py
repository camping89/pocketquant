"""ListSymbolsQuery — list subscriptions, optionally filtered by strategy_code."""

from pydantic import BaseModel


class ListSymbolsQuery(BaseModel):
    """List subscriptions with backtest status, optionally filtered by strategy template."""

    strategy_code: str | None = None
