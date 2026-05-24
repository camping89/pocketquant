"""Command to subscribe to real-time quotes for a composite symbol."""

from pydantic import BaseModel


class SubscribeCommand(BaseModel):
    """Subscribe to real-time quotes. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
