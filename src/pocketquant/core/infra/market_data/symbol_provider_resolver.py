"""Turn a composite symbol into the ordered provider ids that serve it.

Both routing adapters need the same answer and the same treatment of a symbol
that has no ``symbols`` document yet, so neither owns it.

**Seeding must precede the first sync.** A symbol with no record is assumed to
be :data:`UNSEEDED_SYMBOL_ASSET_CLASS`, because that is the only class that can
legitimately arrive unseeded: ``SyncService._persist_bars`` calls
``SymbolRepository.touch`` only after bars land, so a crypto symbol's document
is written by its own first successful sync and the assumption corrects itself
within one cycle.

For anything else the assumption does not correct itself, it sticks. A futures
symbol tracked before it is seeded routes to a crypto venue, which has no such
instrument and returns nothing, so ``_persist_bars`` returns early, ``touch``
is never reached, no document is ever written, and the next cycle repeats it —
with ``SymbolLookupHelper`` caching the miss for 60s in between. That is why
the assumption is a named constant with a warning attached rather than an
inline fallback: it is an ordering requirement, not a default.

The warnings here fire once per symbol. They name a cause; they are not the
alarm. A symbol that keeps fetching nothing is already tracked minute by minute
by ``anomaly_log.emit_no_progress``, which escalates on the streak.
"""

from __future__ import annotations

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    resolve_provider_ids,
)
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper

logger = get_logger(__name__)

#: What a symbol with no ``symbols`` document is assumed to be. See the module
#: docstring: this is load-bearing for every non-crypto asset class, which must
#: be seeded before it is first synced.
UNSEEDED_SYMBOL_ASSET_CLASS = AssetClass.CRYPTO_SPOT


class SymbolProviderResolver:
    """Resolve providers for a symbol, making the unseeded assumption audible."""

    def __init__(self, settings: Settings, symbol_lookup: SymbolLookupHelper) -> None:
        self._settings = settings
        self._symbol_lookup = symbol_lookup
        self._warned_unseeded: set[str] = set()
        self._warned_no_provider: set[str] = set()

    async def provider_ids(self, symbol: str) -> list[str]:
        """Ordered provider ids for ``symbol``, primary first; ``[]`` when none."""
        key = symbol.upper()
        record = await self._symbol_lookup.get(symbol)

        if record is None:
            self._warn_once(
                self._warned_unseeded,
                key,
                "market_data.routing.unseeded_symbol",
                symbol=key,
                assumed_asset_class=UNSEEDED_SYMBOL_ASSET_CLASS.value,
            )
            asset_class = UNSEEDED_SYMBOL_ASSET_CLASS
        else:
            asset_class = record.asset_class

        ids = resolve_provider_ids(
            symbol,
            asset_class,
            self._settings.market_data_providers,
            self._settings.symbol_provider_overrides,
        )

        if not ids:
            # Reachable by configuration, not only by an unmapped class: setting
            # MARKET_DATA_PROVIDERS replaces the whole mapping instead of merging
            # into it, so an override naming one asset class leaves the rest with
            # nothing. Silently fetching no bars looks identical to a dead venue.
            self._warn_once(
                self._warned_no_provider,
                key,
                "market_data.routing.no_provider",
                symbol=key,
                asset_class=asset_class.value,
            )

        return ids

    @staticmethod
    def _warn_once(seen: set[str], key: str, event: str, **fields: object) -> None:
        # Once per symbol, not once per fetch — this sits on the per-minute sync
        # path, where a repeated WARNING would scale with the symbol count.
        if key in seen:
            return
        seen.add(key)
        logger.warning(event, **fields)
