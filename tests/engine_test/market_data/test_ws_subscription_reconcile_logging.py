"""The reconcile loop runs every 5s, so what it logs per tick is multiplied by it.

A tracked symbol that no realtime provider serves — an index future before a quote
adapter exists — fails to subscribe on every tick. That is a configured state, not
a transient fault: it must be said once at WARNING, and must not be reported as an
INFO change on every tick either.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog
from structlog.testing import capture_logs

from pocketquant.engine.market_data.app_services import ws_subscription_app_service as module
from pocketquant.engine.market_data.app_services.ws_subscription_app_service import (
    WsSubscriptionAppService,
)

CRYPTO = "BTCUSDT:BINANCE"
FUTURE = "ES1!:CME_MINI"


class _FakeProvider:
    """Subscribes everything except the symbols listed as unservable."""

    def __init__(self, unservable: set[str]) -> None:
        self.subscriptions: dict[str, object] = {}
        self._unservable = unservable

    async def subscribe(self, symbol: str, callback: object) -> str:
        if symbol in self._unservable:
            raise ValueError(f"No realtime provider registered for {symbol}")
        self.subscriptions[symbol] = callback
        return symbol

    async def unsubscribe(self, symbol: str) -> None:
        self.subscriptions.pop(symbol, None)


def _service(provider: _FakeProvider, tracked: list[str]) -> WsSubscriptionAppService:
    repo = MagicMock()
    repo.list_all = AsyncMock(
        side_effect=lambda: [SimpleNamespace(symbol=s) for s in tracked]
    )
    return WsSubscriptionAppService(
        provider=provider,  # type: ignore[arg-type]
        tracked_symbol_repo=repo,
        quote_app_service=MagicMock(),
    )


@pytest.fixture(autouse=True)
def _fresh_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    # A module logger first used inside capture_logs() stays cached to that
    # configuration and silently stops being capturable in later tests.
    monkeypatch.setattr(module, "logger", structlog.get_logger("test.ws_reconcile"))


def _events(logs: list[dict], event: str, level: str) -> list[dict]:
    return [e for e in logs if e["event"] == event and e["log_level"] == level]


async def test_an_unservable_symbol_warns_once_across_many_ticks() -> None:
    service = _service(_FakeProvider(unservable={FUTURE}), [CRYPTO, FUTURE])

    with capture_logs() as logs:
        for _ in range(5):
            await service._reconcile()

    warnings = _events(logs, "ws_subscription_manager.subscribe_failed", "warning")
    assert [w["symbol"] for w in warnings] == [FUTURE]


async def test_a_failing_symbol_is_not_reported_as_a_change_every_tick() -> None:
    provider = _FakeProvider(unservable={FUTURE})
    service = _service(provider, [CRYPTO, FUTURE])

    with capture_logs() as logs:
        for _ in range(5):
            await service._reconcile()

    reconciled = _events(logs, "ws_subscription_manager.reconciled", "info")
    # Only the first tick changed anything: the crypto symbol subscribed.
    assert [(r["added"], r["removed"]) for r in reconciled] == [(1, 0)]
    assert set(provider.subscriptions) == {CRYPTO}


async def test_a_symbol_tracked_again_after_removal_warns_again() -> None:
    tracked = [FUTURE]
    service = _service(_FakeProvider(unservable={FUTURE}), tracked)

    with capture_logs() as logs:
        await service._reconcile()
        tracked.clear()
        await service._reconcile()
        tracked.append(FUTURE)
        await service._reconcile()

    warnings = _events(logs, "ws_subscription_manager.subscribe_failed", "warning")
    assert len(warnings) == 2


async def test_a_symbol_that_recovers_then_fails_again_warns_again() -> None:
    unservable = {FUTURE}
    provider = _FakeProvider(unservable=unservable)
    service = _service(provider, [FUTURE])

    with capture_logs() as logs:
        await service._reconcile()
        unservable.clear()
        await service._reconcile()
        provider.subscriptions.clear()  # the feed dropped it
        unservable.add(FUTURE)
        await service._reconcile()

    warnings = _events(logs, "ws_subscription_manager.subscribe_failed", "warning")
    assert len(warnings) == 2
