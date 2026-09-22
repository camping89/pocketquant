"""Which data providers serve a symbol, in priority order.

Both routing adapters — REST history and realtime quotes — need the same
answer, so neither owns the rule. Keeping it here also keeps it testable
without constructing an adapter.
"""

from __future__ import annotations

from pocketquant.core.domain.shared.enums import AssetClass


def resolve_provider_ids(
    symbol: str,
    asset_class: AssetClass,
    provider_map: dict[AssetClass, list[str]],
    overrides: dict[str, list[str]],
) -> list[str]:
    """Ordered provider ids for a composite symbol: primary first, then fallbacks.

    A per-symbol override wins outright rather than extending the asset class
    list: moving one instrument to another venue should not silently keep the
    class default as a fallback. Override keys are upper-cased composite
    symbols, matching how symbols are stored.

    Returns a new list every time, so a caller cannot mutate the settings it
    came from.
    """
    override = overrides.get(symbol.upper())
    if override is not None:
        return list(override)
    return list(provider_map.get(asset_class, []))
