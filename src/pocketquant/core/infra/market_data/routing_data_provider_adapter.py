"""Route REST history to the provider each symbol's suffix names.

Implements ``IDataProviderPort`` itself, so the fetch path above it is
unchanged: ``fetch_with_retry`` still sees one provider and one coroutine.
"""

from __future__ import annotations

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    UnknownDataProviderError,
    provider_id_for,
)
from pocketquant.core.domain.shared.enums import Interval

logger = get_logger(__name__)

#: Symbol search has no symbol to route by, so it asks this provider.
DEFAULT_SEARCH_PROVIDER_ID = "binance"


class RoutingDataProviderAdapter(IDataProviderPort):
    """Send each fetch to the one provider the symbol's suffix names."""

    def __init__(
        self,
        providers: dict[str, IDataProviderPort],
        search_provider_id: str = DEFAULT_SEARCH_PROVIDER_ID,
    ) -> None:
        self._providers = providers
        self._search_provider_id = search_provider_id

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[Bar]:
        """Bars from the provider ``symbol`` names.

        There is no fallback: another provider's bars for the same code would
        be a different instrument's prices. A provider failure propagates
        rather than being reported as an empty market, because an outage and a
        quiet venue are different events and only the caller can tell that
        difference to a human.

        This call is nested inside ``fetch_with_retry``'s retry loop, so a
        caller that can reach a legitimately empty market must gate on the
        trading calendar before arriving here — see
        ``sync_jobs._sync_by_intervals``.

        Raises:
            UnknownDataProviderError: when the suffix names no registered
                provider.
        """
        provider = self._provider_for(symbol)
        return await provider.fetch_ohlcv(symbol=symbol, interval=interval, n_bars=n_bars)

    async def search_symbols(self, query: str) -> list[dict]:
        """Delegate to the default search provider.

        Symbol search stays single-provider: merging two venues' results needs a
        dedup rule that nothing asks for yet.
        """
        provider = self._providers.get(self._search_provider_id)
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

    def _provider_for(self, symbol: str) -> IDataProviderPort:
        provider_id = provider_id_for(symbol)
        provider = self._providers.get(provider_id)
        if provider is None:
            raise UnknownDataProviderError(
                f"No data provider registered for {symbol}: suffix names {provider_id!r}"
            )
        return provider
