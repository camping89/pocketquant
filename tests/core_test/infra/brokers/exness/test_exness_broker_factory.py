"""BrokerFactory builds an Exness broker only when live trading is on and configured."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.brokers.exness.exness_broker_adapter import ExnessBrokerAdapter
from pocketquant.core.infra.brokers.exness.exness_safeguards import Safeguards


def _safeguards(live_trading: bool = True) -> Safeguards:
    return Safeguards(
        live_trading=live_trading,
        daily_loss_cap=50.0,
        max_lots=None,
        leverage=1.0,
        risk_per_trade=0.02,
    )


@pytest.mark.parametrize("safeguards", [None, _safeguards(live_trading=False)])
def test_exness_refused_while_live_trading_is_off(safeguards: Safeguards | None) -> None:
    with pytest.raises(ValueError, match="EXNESS_LIVE_TRADING is false"):
        BrokerFactory(EventBus(), safeguards=safeguards, safeguards_repository=AsyncMock()).create(
            "exness", {}
        )


def test_exness_requires_a_configured_client() -> None:
    factory = BrokerFactory(EventBus(), safeguards=_safeguards(), safeguards_repository=AsyncMock())

    with pytest.raises(ValueError, match="requires EXNESS_\\* settings"):
        factory.create("exness", {})


def test_exness_built_when_live_and_configured() -> None:
    client = MagicMock(is_configured=True)
    factory = BrokerFactory(
        EventBus(),
        exness_client=client,
        position_repository=MagicMock(),
        safeguards=_safeguards(),
        safeguards_repository=AsyncMock(),
    )

    broker = factory.create("exness", {})

    assert isinstance(broker, ExnessBrokerAdapter)
