"""Command to unsubscribe from real-time quotes for a composite symbol."""

from pydantic import BaseModel


class UnsubscribeCommand(BaseModel):
    """Unsubscribe from real-time quotes. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
