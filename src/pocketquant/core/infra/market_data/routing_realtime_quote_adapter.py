from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    UnknownDataProviderError,
    provider_id_for,
)
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)

logger = get_logger(__name__)


class RoutingRealtimeQuoteAdapter:
    def __init__(
        self,
        providers: dict[str, IRealtimeQuoteProviderPort],
    ) -> None:
        self._providers = providers
        self._owner: dict[str, str] = {}

    # The port declares this read-only, which lets it be derived here instead of stored.
    @property
    def last_tick_at(self) -> datetime | None:
        ticks = [p.last_tick_at for p in self._providers.values() if p.last_tick_at is not None]
        return max(ticks) if ticks else None

    async def connect(self) -> None:
        for provider in self._providers.values():
            await provider.connect()

    async def disconnect(self) -> None:
        # Swallow per child: one bad socket must not block shutdown of the rest.
        for provider_id, provider in self._providers.items():
            try:
                await provider.disconnect()
            except Exception as exc:
                logger.warning(
                    "market_data.routing.disconnect_failed",
                    provider=provider_id,
                    error=str(exc),
                )

    # Never a second provider: two feeds for one symbol would both reach
    # BarBuilderDomainService and silently double-count its ticks.
    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> str:
        provider_id = provider_id_for(symbol)
        provider = self._providers.get(provider_id)
        if provider is None:
            raise UnknownDataProviderError(
                f"No realtime provider registered for {symbol}: suffix names {provider_id!r}"
            )

        key = await provider.subscribe(symbol=symbol, callback=callback)
        self._owner[symbol.upper()] = provider_id
        return key

    async def unsubscribe(self, symbol: str) -> None:
        provider_id = self._owner.pop(symbol.upper(), None)
        provider = self._providers.get(provider_id) if provider_id else None
        if provider is None:
            return
        await provider.unsubscribe(symbol)

    async def run_forever(self) -> None:
        # CancelledError propagates so lifespan teardown still works.
        await asyncio.gather(*(p.run_forever() for p in self._providers.values()))

    def is_connected(self) -> bool:
        return any(p.is_connected() for p in self._providers.values())

    @property
    def subscription_count(self) -> int:
        return sum(p.subscription_count for p in self._providers.values())

    # WsSubscriptionAppService._reconcile diffs against these keys, so a child missing here
    # would be resubscribed forever.
    @property
    def subscriptions(self) -> dict:
        merged: dict = {}
        for provider in self._providers.values():
            merged.update(provider.subscriptions)
        return merged
