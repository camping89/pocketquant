"""Quote commands."""

from pydantic import BaseModel, Field


class SubscribeCommand(BaseModel):
    """Subscribe to real-time quotes for a symbol."""

    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")


class UnsubscribeCommand(BaseModel):
    """Unsubscribe from real-time quotes for a symbol."""

    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")


class StartQuoteFeedCommand(BaseModel):
    """Start the quote WebSocket feed."""

    pass


class StopQuoteFeedCommand(BaseModel):
    """Stop the quote WebSocket feed."""

    pass
