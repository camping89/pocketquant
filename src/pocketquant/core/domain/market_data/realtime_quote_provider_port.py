"""Realtime quote provider port — WebSocket-based tick stream interface.

Neutral domain location so no concrete provider implementation (Binance, OKX,
Kraken, etc.) is implied by the module path.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IRealtimeQuoteProviderPort(Protocol):
    """Protocol for realtime WebSocket-based quote providers.

    Using Protocol (not ABC) so future providers (OKX, Kraken, etc.) satisfy the
    interface via structural subtyping without inheritance. @runtime_checkable
    enables isinstance() checks in DI tests and guard assertions.

    9 required members — all concrete providers must expose these to satisfy DI
    type resolution and runtime isinstance() checks.
    """

    last_tick_at: datetime | None

    async def connect(self) -> None:
        """Open the WebSocket connection."""
        ...

    async def disconnect(self) -> None: ...

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> str:
        """Register a subscription. ``symbol`` composite ``{code}:{exchange}``. Returns key."""
        ...

    async def unsubscribe(self, symbol: str) -> None:
        """Remove a symbol subscription. ``symbol`` is composite ``{code}:{exchange}``."""
        ...

    async def run_forever(self) -> None: ...

    def is_connected(self) -> bool:
        """Return True when the underlying WebSocket is open."""
        ...

    @property
    def subscription_count(self) -> int: ...

    @property
    def subscriptions(self) -> dict: ...
