from __future__ import annotations

import pytest

from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    DATA_PROVIDER_DEFAULTS,
    DataProviderDefaults,
    UnknownDataProviderError,
    provider_defaults_for,
    provider_id_for,
    unseeded_symbol,
)
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol import LINEAR_SPEC
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_CRYPTO_24_7,
    CALENDAR_EXNESS_FX,
)


@pytest.mark.parametrize(
    ("symbol", "provider_id"),
    [
        ("BTCUSDT:BINANCE", "binance"),
        ("XAUUSD:EXNESS", "exness"),
        ("btcusdt:binance", "binance"),
        ("eurusd:exness", "exness"),
    ],
)
def test_the_provider_id_is_the_lower_cased_suffix(symbol: str, provider_id: str) -> None:
    assert provider_id_for(symbol) == provider_id


@pytest.mark.parametrize("symbol", ["BTCUSDT", "BTCUSDT:", ""])
def test_a_symbol_without_a_suffix_names_no_provider(symbol: str) -> None:
    with pytest.raises(UnknownDataProviderError):
        provider_id_for(symbol)


def test_binance_defaults_to_crypto_spot_on_a_24x7_calendar() -> None:
    defaults = provider_defaults_for("DOGEUSDT:BINANCE")

    assert defaults.asset_class is AssetClass.CRYPTO_SPOT
    assert defaults.calendar_id == CALENDAR_CRYPTO_24_7


# A gold symbol must never be assumed to trade 24/7 like crypto.
def test_an_unregistered_provider_has_no_defaults_rather_than_crypto_ones() -> None:
    with pytest.raises(UnknownDataProviderError, match="'mt5'"):
        provider_defaults_for("XAUUSD:MT5")


def test_exness_defaults_to_a_cfd_on_the_exness_fx_calendar() -> None:
    assert provider_defaults_for("XAUUSD:EXNESS") == DataProviderDefaults(
        AssetClass.CFD, "EXNESS_FX"
    )


def test_an_unseeded_symbol_is_described_by_its_provider() -> None:
    symbol = unseeded_symbol("eurusd:exness")

    assert symbol.symbol == "EURUSD:EXNESS"
    assert symbol.asset_class is AssetClass.CFD
    assert symbol.calendar_id == CALENDAR_EXNESS_FX
    assert symbol.contract_spec == LINEAR_SPEC


def test_exactly_the_registered_providers_have_defaults() -> None:
    assert set(DATA_PROVIDER_DEFAULTS) == {"binance", "exness"}
