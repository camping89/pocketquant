"""Command to subscribe to real-time quotes for a symbol."""

from pydantic import BaseModel


class SubscribeCommand(BaseModel):
    """Subscribe to real-time quotes for a symbol."""

    symbol: str
    exchange: str
