"""Get all quotes query and handler."""

from pocketquant.api.market_data.handlers.quotes.get_all.handler import GetAllQuotesHandler
from pocketquant.api.market_data.handlers.quotes.get_all.query import GetAllQuotesQuery

__all__ = ["GetAllQuotesQuery", "GetAllQuotesHandler"]
