"""Unit tests: DI container wires BinanceClient → IDataProvider and
BinanceWebSocketClient → IRealtimeQuoteProvider.

These tests use minimal Dishka providers — no real MongoDB/Redis needed.
We stub Settings and verify concrete types returned by the provider methods.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pocketquant.app.di.infrastructure import InfrastructureProvider
from pocketquant.app.di.market_data import MarketDataProvider
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.interfaces import IDataProvider, IRealtimeQuoteProvider
from pocketquant.infrastructure.market_data.binance.binance_client import BinanceClient
from pocketquant.infrastructure.market_data.binance.binance_websocket_client import (
    BinanceWebSocketClient,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Minimal Settings mock — only fields used by BinanceClient constructor."""
    s = MagicMock(spec=Settings)
    return s


def test_get_data_provider_returns_binance_client(mock_settings: Settings) -> None:
    """InfrastructureProvider.get_data_provider must return a BinanceClient."""
    provider = InfrastructureProvider()
    result = provider.get_data_provider(mock_settings)

    assert isinstance(result, BinanceClient), f"Expected BinanceClient, got {type(result).__name__}"


def test_get_data_provider_satisfies_idataprovider_abc(mock_settings: Settings) -> None:
    """BinanceClient returned by DI must be a subclass of IDataProvider ABC."""
    provider = InfrastructureProvider()
    result = provider.get_data_provider(mock_settings)

    assert isinstance(result, IDataProvider), "BinanceClient must satisfy IDataProvider ABC"


def test_get_realtime_quote_provider_returns_binance_ws_client() -> None:
    """MarketDataProvider.get_realtime_quote_provider must return a BinanceWebSocketClient."""
    provider = MarketDataProvider()
    result = provider.get_realtime_quote_provider()

    assert isinstance(result, BinanceWebSocketClient), (
        f"Expected BinanceWebSocketClient, got {type(result).__name__}"
    )


def test_get_realtime_quote_provider_satisfies_protocol() -> None:
    """BinanceWebSocketClient must satisfy IRealtimeQuoteProvider Protocol (runtime_checkable)."""
    provider = MarketDataProvider()
    result = provider.get_realtime_quote_provider()

    assert isinstance(result, IRealtimeQuoteProvider), (
        "BinanceWebSocketClient must satisfy IRealtimeQuoteProvider Protocol"
    )
