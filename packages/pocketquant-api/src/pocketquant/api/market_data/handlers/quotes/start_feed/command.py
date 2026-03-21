"""Command to start the real-time quote WebSocket feed."""

from pydantic import BaseModel


class StartQuoteFeedCommand(BaseModel):
    """Start the real-time quote WebSocket feed."""

    pass
