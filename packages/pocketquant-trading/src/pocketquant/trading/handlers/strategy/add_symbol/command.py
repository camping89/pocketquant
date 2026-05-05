"""AddSymbolCommand — subscribe a strategy to a (symbol, exchange, interval) tuple."""

from pydantic import BaseModel


class AddSymbolCommand(BaseModel):
    """Command to add a symbol subscription to a loaded strategy."""

    strategy_id: str
    symbol: str
    exchange: str
    interval: str  # e.g. "1h", "5m", "1d"
