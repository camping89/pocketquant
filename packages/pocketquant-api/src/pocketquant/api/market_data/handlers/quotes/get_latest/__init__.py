"""Get latest quote query and handler."""

from pocketquant.api.market_data.handlers.quotes.get_latest.handler import GetLatestQuoteHandler
from pocketquant.api.market_data.handlers.quotes.get_latest.query import GetLatestQuoteQuery

__all__ = ["GetLatestQuoteQuery", "GetLatestQuoteHandler"]
