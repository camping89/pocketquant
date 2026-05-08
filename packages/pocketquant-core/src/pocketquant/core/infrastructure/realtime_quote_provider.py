"""IRealtimeQuoteProvider — structural Protocol for realtime WebSocket quote providers.

Using Protocol (not ABC) so future providers (OKX, Kraken, etc.) can satisfy the
interface via structural subtyping without inheritance. @runtime_checkable enables
isinstance() checks in DI tests and guard assertions.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IRealtimeQuoteProvider(Protocol):
    """Protocol for realtime WebSocket-based quote providers.

    9 required members — all concrete providers must expose these to satisfy DI
    type resolution and runtime isinstance() checks.
    """

    last_tick_at: datetime | None

    async def connect(self) -> None:
        """Open the WebSocket connection."""
        ...

    async def disconnect(self) -> None:
        """Close connection and stop the run loop."""
        ...

    async def subscribe(
        self,
        symbol: str,
        exchange: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> str:
        """Register a symbol subscription. Returns the symbol_key."""
        ...

    async def unsubscribe(self, symbol: str, exchange: str) -> None:
        """Remove a symbol subscription."""
        ...

    async def run_forever(self) -> None:
        """Start the receive loop; reconnects on connection drop."""
        ...

    def is_connected(self) -> bool:
        """Return True when the underlying WebSocket is open."""
        ...

    @property
    def subscription_count(self) -> int:
        """Number of active symbol subscriptions."""
        ...

    @property
    def subscriptions(self) -> dict:
        """Active subscriptions mapping (symbol_key → implementation-specific value)."""
        ...
