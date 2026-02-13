"""Get all quotes query and handler."""

from src.features.market_data.quotes.get_all.handler import GetAllQuotesHandler
from src.features.market_data.quotes.get_all.query import GetAllQuotesQuery

__all__ = ["GetAllQuotesQuery", "GetAllQuotesHandler"]
