"""Get completed trades (closed positions) for a strategy/subscription instance."""

from pocketquant.trading.handlers.strategy.get_trades.handler import (
    GetStrategyTradesHandler,
)
from pocketquant.trading.handlers.strategy.get_trades.query import (
    GetStrategyTradesQuery,
)

__all__ = ["GetStrategyTradesHandler", "GetStrategyTradesQuery"]
