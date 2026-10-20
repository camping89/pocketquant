"""BrokerFactory builds an Exness broker only when live trading is on and configured."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.brokers.exness.exness_broker_adapter import ExnessBrokerAdapter


def test_exness_refused_while_live_trading_is_off() -> None:
    with pytest.raises(ValueError, match="EXNESS_LIVE_TRADING is false"):
        BrokerFactory(EventBus()).create("exness", {})


def test_exness_requires_a_configured_client() -> None:
    factory = BrokerFactory(EventBus(), exness_live_trading=True)

    with pytest.raises(ValueError, match="requires EXNESS_\\* settings"):
        factory.create("exness", {})


def test_exness_built_when_live_and_configured() -> None:
    client = MagicMock(is_configured=True)
    factory = BrokerFactory(
        EventBus(),
        exness_client=client,
        position_repository=MagicMock(),
        exness_live_trading=True,
    )

    broker = factory.create("exness", {"exness_daily_loss_cap": 50.0})

    assert isinstance(broker, ExnessBrokerAdapter)
