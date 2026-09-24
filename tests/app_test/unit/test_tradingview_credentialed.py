"""Whether the health check treats TradingView as a provider that should hold a session."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from pocketquant.app.main_extensions import _tradingview_credentialed
from pocketquant.core.domain.shared.enums import AssetClass
from tests.core_test.infra.market_data.conftest import build_settings


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, False),
        ({"tradingview_username": "someone"}, False),
        ({"tradingview_username": "someone", "tradingview_password": SecretStr("pw")}, True),
        ({"tradingview_auth_token": SecretStr("token")}, True),
    ],
)
def test_only_a_configured_login_expects_a_session(fields: dict, expected: bool) -> None:
    settings = build_settings({AssetClass.CRYPTO_SPOT: ["binance"]}).model_copy(update=fields)

    assert _tradingview_credentialed(settings) is expected
