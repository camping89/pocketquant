"""Route REST history to the providers that serve each symbol.

Implements ``IDataProviderPort`` itself, so the fetch path above it is
unchanged: ``fetch_with_retry`` still sees one provider and one coroutine.
"""

from __future__ import annotations

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.shared.enums import AssetClass, Interval
from pocketquant.core.infra.market_data.symbol_provider_resolver import SymbolProviderResolver
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper

logger = get_logger(__name__)


class RoutingDataProviderAdapter(IDataProviderPort):
    """Try each provider that serves a symbol in turn, primary first."""

    def __init__(
        self,
        providers: dict[str, IDataProviderPort],
        settings: Settings,
        symbol_lookup: SymbolLookupHelper,
    ) -> None:
        self._providers = providers
        self._settings = settings
        self._resolver = SymbolProviderResolver(settings=settings, symbol_lookup=symbol_lookup)
        self._warned_unknown: set[str] = set()

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[Bar]:
        """Bars from the first provider that returns any; ``[]`` when none does.

        An exception or an empty answer falls through to the next provider.
        Note that this loop is nested inside ``fetch_with_retry``'s retry loop,
        so the callers that can reach a legitimately empty market must gate on
        the trading calendar before they get here — see
        ``sync_jobs._sync_by_intervals``.
        """
        provider_ids = await self._resolver.provider_ids(symbol)

        for position, provider_id in enumerate(provider_ids):
            next_id = provider_ids[position + 1] if position + 1 < len(provider_ids) else None
            provider = self._providers.get(provider_id)
            if provider is None:
                self._warn_unknown(provider_id, symbol)
                continue

            try:
                bars = await provider.fetch_ohlcv(
                    symbol=symbol,
                    interval=interval,
                    n_bars=n_bars,
                )
            except Exception as exc:
                # DEBUG, not INFO: this runs once per symbol per interval per minute.
                logger.debug(
                    "market_data.routing.fallback",
                    symbol=symbol,
                    provider=provider_id,
                    next_provider=next_id,
                    reason="error",
                    error=str(exc),
                )
                continue

            if bars:
                return bars

            logger.debug(
                "market_data.routing.fallback",
                symbol=symbol,
                provider=provider_id,
                next_provider=next_id,
                reason="empty",
            )

        return []

    async def search_symbols(self, query: str) -> list[dict]:
        """Delegate to the first crypto-spot provider.

        Symbol search stays single-provider: merging two venues' results needs a
        dedup rule that nothing asks for yet.
        """
        ids = self._settings.market_data_providers.get(AssetClass.CRYPTO_SPOT, [])
        provider = self._providers.get(ids[0]) if ids else None
        if provider is None:
            return []
        return await provider.search_symbols(query)

    async def close(self) -> None:
        """Close every child, then re-raise the first failure.

        One child failing to close must not leave the others' sockets open.
        """
        first: Exception | None = None
        for provider_id, provider in self._providers.items():
            try:
                await provider.close()
            except Exception as exc:
                logger.warning(
                    "market_data.routing.close_failed",
                    provider=provider_id,
                    error=str(exc),
                )
                if first is None:
                    first = exc
        if first is not None:
            raise first

    def _warn_unknown(self, provider_id: str, symbol: str) -> None:
        # Once per id, not once per fetch — this sits on the per-minute sync path.
        if provider_id in self._warned_unknown:
            return
        self._warned_unknown.add(provider_id)
        logger.warning(
            "market_data.routing.unknown_provider",
            provider=provider_id,
            symbol=symbol,
        )
