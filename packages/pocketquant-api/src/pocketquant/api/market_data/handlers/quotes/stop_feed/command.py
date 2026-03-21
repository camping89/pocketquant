"""Command to stop the real-time quote WebSocket feed."""

from pydantic import BaseModel


class StopQuoteFeedCommand(BaseModel):
    """Stop the real-time quote WebSocket feed."""

    pass
