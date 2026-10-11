"""Unit tests: DI builds the policy registry whose Binance policy carries BinanceClient
as its IDataProvider and BinanceWebSocketClient as its IRealtimeQuoteProvider.

These tests use the provider method directly — no real MongoDB/Redis needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pocketquant.app.di.infrastructure import InfrastructureProvider
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.interfaces import IDataProvider, IRealtimeQuoteProvider
from pocketquant.core.infra.binance.binance_client import BinanceClient
from pocketquant.core.infra.binance.binance_websocket_client import (
    BinanceWebSocketClient,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Minimal Settings mock — only fields used by BinanceClient constructor."""
    s = MagicMock(spec=Settings)
    return s


def test_binance_policy_data_provider_is_binance_client(mock_settings: Settings) -> None:
    policy = InfrastructureProvider().get_sync_policies(mock_settings).policy_for("BTCUSDT:BINANCE")

    assert policy is not None
    assert isinstance(policy.data_provider, BinanceClient)
    assert isinstance(policy.data_provider, IDataProvider)


def test_binance_policy_quote_provider_is_binance_ws_client(mock_settings: Settings) -> None:
    policy = InfrastructureProvider().get_sync_policies(mock_settings).policy_for("BTCUSDT:BINANCE")

    assert policy is not None
    assert isinstance(policy.quote_provider, BinanceWebSocketClient)
    assert isinstance(policy.quote_provider, IRealtimeQuoteProvider)
