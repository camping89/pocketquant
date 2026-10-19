"""Which data provider serves a symbol: the composite symbol's suffix names it.

``BTCUSDT:BINANCE`` is served by ``binance`` and ``ES1!:TRADINGVIEW`` by
``tradingview``: the suffix is the provider id, upper-cased in full. The
execution broker is a separate, per-strategy setting and plays no part here.

Both routing adapters — REST history and realtime quotes — need the same
answer, so neither owns the rule. Keeping it here also keeps it testable
without constructing an adapter.

A symbol with no ``symbols`` document yet takes its asset class and calendar
from its provider's defaults, so an unseeded symbol is described by where its
bars come from rather than assumed to be crypto.
"""

from __future__ import annotations

from dataclasses import dataclass

from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_CME_GLOBEX_EQUITY,
    CALENDAR_CRYPTO_24_7,
    CALENDAR_EXNESS_FX,
)


class UnknownDataProviderError(ValueError):
    """The symbol's suffix names no registered data provider."""


@dataclass(frozen=True)
class DataProviderDefaults:
    """What an unseeded symbol from this provider is assumed to be."""

    asset_class: AssetClass
    calendar_id: str


# One entry per registered data provider, keyed by provider id. A provider that
# serves several asset classes still needs one default here; seeding the symbol
# is how a different asset class or calendar is recorded.
DATA_PROVIDER_DEFAULTS: dict[str, DataProviderDefaults] = {
    "binance": DataProviderDefaults(AssetClass.CRYPTO_SPOT, CALENDAR_CRYPTO_24_7),
    "tradingview": DataProviderDefaults(AssetClass.INDEX_FUTURE, CALENDAR_CME_GLOBEX_EQUITY),
    "exness": DataProviderDefaults(AssetClass.CFD, CALENDAR_EXNESS_FX),
}


def provider_id_for(symbol: str) -> str:
    """The provider id a composite symbol names: its suffix, lower-cased.

    Raises:
        UnknownDataProviderError: when the symbol carries no suffix.
    """
    _, separator, suffix = symbol.rpartition(":")
    if not separator or not suffix:
        raise UnknownDataProviderError(
            f"{symbol!r} names no data provider; expected '{{CODE}}:{{PROVIDER}}'"
        )
    return suffix.lower()


def provider_defaults_for(symbol: str) -> DataProviderDefaults:
    """The defaults of the provider ``symbol`` names.

    Raises:
        UnknownDataProviderError: when the suffix is not a registered provider.
            Guessing would give, say, a gold symbol a 24/7 crypto calendar.
    """
    provider_id = provider_id_for(symbol)
    defaults = DATA_PROVIDER_DEFAULTS.get(provider_id)
    if defaults is None:
        raise UnknownDataProviderError(
            f"{symbol!r} names data provider {provider_id!r}, which is not registered"
        )
    return defaults


def unseeded_symbol(symbol: str) -> Symbol:
    """The record an unseeded symbol is assumed to have, from its provider."""
    defaults = provider_defaults_for(symbol)
    return Symbol.create(
        symbol=symbol,
        asset_class=defaults.asset_class,
        calendar_id=defaults.calendar_id,
    )
