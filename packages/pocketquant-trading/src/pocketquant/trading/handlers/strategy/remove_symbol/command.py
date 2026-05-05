"""RemoveSymbolCommand — delete a single subscription and its cached backtest."""

from pydantic import BaseModel


class RemoveSymbolCommand(BaseModel):
    """Command to remove a symbol subscription from a strategy."""

    strategy_id: str
    sub_id: str
