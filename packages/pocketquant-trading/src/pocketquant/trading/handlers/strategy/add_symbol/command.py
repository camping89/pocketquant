"""AddSymbolCommand — subscribe a strategy to a (symbol, interval) tuple."""

from pydantic import BaseModel


class AddSymbolCommand(BaseModel):
    """Command to add a symbol subscription to a loaded strategy.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    strategy_id: str
    symbol: str
    interval: str  # e.g. "1h", "5m", "1d"
