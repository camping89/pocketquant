from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


# Protocol so providers match structurally; runtime_checkable for isinstance() checks in
# DI tests and guards.
@runtime_checkable
class IRealtimeQuoteProviderPort(Protocol):
    # Read-only on purpose: a mutable declaration would force every provider to expose a
    # settable attribute, ruling out one that derives the value.
    @property
    def last_tick_at(self) -> datetime | None: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> str: ...

    async def unsubscribe(self, symbol: str) -> None: ...

    async def run_forever(self) -> None: ...

    def is_connected(self) -> bool: ...

    @property
    def subscription_count(self) -> int: ...

    @property
    def subscriptions(self) -> dict: ...
