# Both routing adapters (REST history and realtime quotes) need this answer, so neither
# owns the rule. The execution broker is a separate per-strategy setting.

from __future__ import annotations

from dataclasses import dataclass

from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_CRYPTO_24_7,
    CALENDAR_EXNESS_FX,
)


class UnknownDataProviderError(ValueError): ...


@dataclass(frozen=True)
class DataProviderDefaults:
    asset_class: AssetClass
    calendar_id: str


# One entry per registered data provider, keyed by provider id. A provider that
# serves several asset classes still needs one default here; seeding the symbol
# is how a different asset class or calendar is recorded.
DATA_PROVIDER_DEFAULTS: dict[str, DataProviderDefaults] = {
    "binance": DataProviderDefaults(AssetClass.CRYPTO_SPOT, CALENDAR_CRYPTO_24_7),
    "exness": DataProviderDefaults(AssetClass.CFD, CALENDAR_EXNESS_FX),
}


def provider_id_for(symbol: str) -> str:
    _, separator, suffix = symbol.rpartition(":")
    if not separator or not suffix:
        raise UnknownDataProviderError(
            f"{symbol!r} names no data provider; expected '{{CODE}}:{{PROVIDER}}'"
        )
    return suffix.lower()


# Raises on an unknown suffix: guessing would give a gold symbol a 24/7 crypto calendar.
def provider_defaults_for(symbol: str) -> DataProviderDefaults:
    provider_id = provider_id_for(symbol)
    defaults = DATA_PROVIDER_DEFAULTS.get(provider_id)
    if defaults is None:
        raise UnknownDataProviderError(
            f"{symbol!r} names data provider {provider_id!r}, which is not registered"
        )
    return defaults


def unseeded_symbol(symbol: str) -> Symbol:
    defaults = provider_defaults_for(symbol)
    return Symbol.create(
        symbol=symbol,
        asset_class=defaults.asset_class,
        calendar_id=defaults.calendar_id,
    )
