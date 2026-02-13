"""Command to unsubscribe from real-time quotes for a symbol."""

from pydantic import BaseModel


class UnsubscribeCommand(BaseModel):
    """Unsubscribe from real-time quotes for a symbol."""

    symbol: str
    exchange: str
