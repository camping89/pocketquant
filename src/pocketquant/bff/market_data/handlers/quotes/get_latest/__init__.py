"""Get latest quote query and handler."""

from pocketquant.engine.market_data.handlers.quotes.get_latest.handler import (
    GetLatestQuoteHandler,
)
from pocketquant.engine.market_data.handlers.quotes.get_latest.query import GetLatestQuoteQuery

__all__ = ["GetLatestQuoteQuery", "GetLatestQuoteHandler"]
