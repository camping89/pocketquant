"""Route realtime subscriptions to the one provider that owns each symbol.

Satisfies ``IRealtimeQuoteProviderPort`` structurally, so
``WsSubscriptionAppService`` and ``QuoteAppService`` need no edits.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.market_data.symbol_provider_resolver import SymbolProviderResolver
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper

logger = get_logger(__name__)


class RoutingRealtimeQuoteAdapter:
    """Fan connect/run/disconnect across children; route each symbol to one."""

    def __init__(
        self,
        providers: dict[str, IRealtimeQuoteProviderPort],
        settings: Settings,
        symbol_lookup: SymbolLookupHelper,
    ) -> None:
        self._providers = providers
        self._resolver = SymbolProviderResolver(settings=settings, symbol_lookup=symbol_lookup)
        self._owner: dict[str, str] = {}

    @property
    def last_tick_at(self) -> datetime | None:
        """The most recent tick across children.

        The Protocol declares this as a plain attribute; a read-only property
        satisfies structural typing and keeps the value derived rather than
        another thing to keep in sync.
        """
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

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> str:
        """Subscribe through the primary provider only — never a fallback.

        Two realtime feeds for one symbol would both reach
        ``BarBuilderDomainService`` and double-count its ticks, which is worse
        than a missing feed because it is silent.
        """
        provider_id = await self._owner_id_for(symbol)
        provider = self._providers.get(provider_id) if provider_id else None
        if provider is None:
            raise ValueError(
                f"No realtime provider registered for {symbol}: resolved {provider_id or 'nothing'}"
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

    @property
    def subscriptions(self) -> dict:
        """The merged view every child holds.

        ``WsSubscriptionAppService._reconcile`` diffs its desired set against
        these keys, so a child missing from here would be resubscribed forever.
        """
        merged: dict = {}
        for provider in self._providers.values():
            merged.update(provider.subscriptions)
        return merged

    async def _owner_id_for(self, symbol: str) -> str:
        """The single provider that owns this symbol's stream; ``""`` when none."""
        ids = await self._resolver.provider_ids(symbol)
        return ids[0] if ids else ""
