"""WsSubscriptionManager subscribes each tracked symbol through its policy's quote provider
and skips symbols whose exchange has no policy without retrying them every tick."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from structlog.testing import capture_logs

from pocketquant.app.market_data.app_services import ws_subscription_manager
from pocketquant.app.market_data.app_services.ws_subscription_manager import (
    WsSubscriptionManager,
)
from pocketquant.engine.market_data import sync_policy
from pocketquant.engine.market_data.sync_policy import SyncPolicies, binance_policy


class _FakeQuoteProvider:
    def __init__(self) -> None:
        self.subscriptions: dict[str, object] = {}
        self.subscribe = AsyncMock(side_effect=self._subscribe)
        self.unsubscribe = AsyncMock()

    async def _subscribe(self, symbol: str, callback: object) -> str:
        self.subscriptions[symbol] = callback
        return symbol


@pytest.fixture(autouse=True)
def _fresh_loggers(monkeypatch: pytest.MonkeyPatch) -> None:
    import structlog

    for module in (sync_policy, ws_subscription_manager):
        monkeypatch.setattr(module, "logger", structlog.get_logger(module.__name__))


@pytest.mark.asyncio
async def test_reconcile_subscribes_known_exchange_and_skips_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ws_subscription_manager, "_SUBSCRIBE_DELAY_S", 0)
    quotes = _FakeQuoteProvider()
    policies = SyncPolicies([binance_policy(data_provider=MagicMock(), quote_provider=quotes)])  # type: ignore[arg-type]
    repo = MagicMock()
    repo.list_all = AsyncMock(
        return_value=[
            SimpleNamespace(symbol="BTCUSDT:BINANCE"),
            SimpleNamespace(symbol="ETHUSDT:OKX"),
        ]
    )
    manager = WsSubscriptionManager(
        policies=policies,
        tracked_symbol_repo=repo,
        quote_app_service=MagicMock(on_quote_update=AsyncMock()),
    )

    with capture_logs() as logs:
        for _ in range(3):
            await manager._reconcile()

    quotes.subscribe.assert_awaited_once_with(symbol="BTCUSDT:BINANCE", callback=ANY)
    quotes.unsubscribe.assert_not_called()
    unknown = [e for e in logs if e["event"] == "market_data.unknown_exchange"]
    assert len(unknown) == 1
    assert unknown[0]["exchange"] == "OKX"
