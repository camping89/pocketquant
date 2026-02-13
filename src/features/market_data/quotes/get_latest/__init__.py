"""Get latest quote query and handler."""

from src.features.market_data.quotes.get_latest.handler import GetLatestQuoteHandler
from src.features.market_data.quotes.get_latest.query import GetLatestQuoteQuery

__all__ = ["GetLatestQuoteQuery", "GetLatestQuoteHandler"]
