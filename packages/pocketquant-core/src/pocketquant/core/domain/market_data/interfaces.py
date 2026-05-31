"""Market-data provider ports — REST/historical (IDataProvider) and realtime (IRealtimeQuoteProvider).

Neutral domain location so no concrete provider implementation (Binance, OKX,
TradingView, etc.) is implied by the module path.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.value_objects import Interval


class IDataProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[Bar]:
        """Fetch OHLCV bars from data provider. ``symbol`` is composite ``{code}:{exchange}``."""
        ...

    @abstractmethod
    async def search_symbols(
        self,
        query: str,
    ) -> list[dict]:
        """Search available symbols."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        ...


@runtime_checkable
class IRealtimeQuoteProvider(Protocol):
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

    async def disconnect(self) -> None:
        """Close connection and stop the run loop."""
        ...

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> str:
        """Register a symbol subscription. ``symbol`` is composite ``{code}:{exchange}``. Returns key."""
        ...

    async def unsubscribe(self, symbol: str) -> None:
        """Remove a symbol subscription. ``symbol`` is composite ``{code}:{exchange}``."""
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
