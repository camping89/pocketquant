"""Short-lived symbol cache for per-bar callers.

Calendar resolution happens once per bar on every sync and cascade path, and
a symbol's asset class changes about as often as never. A 60-second TTL keeps
that off the database without making a re-seeded symbol wait for a restart.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import cast

from cachetools import TTLCache

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository

logger = get_logger(__name__)

# cast: TTLCache.__init__ does not propagate its generic parameters.
_CACHE = cast("MutableMapping[str, Symbol | None]", TTLCache(maxsize=500, ttl=60))


class SymbolLookupHelper:
    """Read-through cache over ``SymbolRepository.find_by_symbol``."""

    def __init__(self, symbol_repository: SymbolRepository) -> None:
        self._repo = symbol_repository

    async def get(self, composite: str) -> Symbol | None:
        key = composite.upper()
        if key in _CACHE:
            return _CACHE[key]

        symbol = await self._repo.find_by_symbol(key)
        # Misses are cached too: an unseeded symbol would otherwise hit the
        # database once per bar, which is the hot path this class exists for.
        _CACHE[key] = symbol
        logger.debug("symbol_lookup.miss", symbol=key, found=symbol is not None)
        return symbol
