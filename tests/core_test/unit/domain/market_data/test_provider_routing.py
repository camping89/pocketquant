"""Pin the provider-resolution rule before any adapter depends on it."""

from __future__ import annotations

from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    resolve_provider_ids,
)
from pocketquant.core.domain.shared.enums import AssetClass

PROVIDER_MAP = {
    AssetClass.CRYPTO_SPOT: ["binance"],
    AssetClass.INDEX_FUTURE: ["tradingview", "binance"],
}


def test_asset_class_map_is_used() -> None:
    assert resolve_provider_ids(
        "ES1!:CME_MINI", AssetClass.INDEX_FUTURE, PROVIDER_MAP, {}
    ) == ["tradingview", "binance"]


def test_symbol_override_beats_asset_class() -> None:
    overrides = {"ES1!:CME_MINI": ["binance"]}

    assert resolve_provider_ids(
        "ES1!:CME_MINI", AssetClass.INDEX_FUTURE, PROVIDER_MAP, overrides
    ) == ["binance"]


def test_override_lookup_is_case_insensitive() -> None:
    overrides = {"ES1!:CME_MINI": ["binance"]}

    assert resolve_provider_ids(
        "es1!:cme_mini", AssetClass.INDEX_FUTURE, PROVIDER_MAP, overrides
    ) == ["binance"]


def test_unmapped_asset_class_returns_empty_list() -> None:
    assert resolve_provider_ids("XBTUSD:DERIBIT", AssetClass.CRYPTO_PERP, PROVIDER_MAP, {}) == []


def test_the_returned_list_is_not_the_stored_one() -> None:
    """A caller mutating the result must not rewrite the settings it came from."""
    provider_map = {AssetClass.CRYPTO_SPOT: ["binance"]}
    overrides = {"ES1!:CME_MINI": ["tradingview"]}

    resolve_provider_ids("BTCUSDT:BINANCE", AssetClass.CRYPTO_SPOT, provider_map, overrides).append(
        "mutated"
    )
    resolve_provider_ids("ES1!:CME_MINI", AssetClass.INDEX_FUTURE, provider_map, overrides).append(
        "mutated"
    )

    assert provider_map[AssetClass.CRYPTO_SPOT] == ["binance"]
    assert overrides["ES1!:CME_MINI"] == ["tradingview"]
