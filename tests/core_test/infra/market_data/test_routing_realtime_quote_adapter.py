# Unlike the REST path there is deliberately no fallback here. Two feeds for one symbol
# would both reach BarBuilderDomainService and double-count its ticks, which is worse than a
# missing feed because nothing reports it.

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    UnknownDataProviderError,
)
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import (
    RoutingRealtimeQuoteAdapter,
)

SYMBOL = "XAUUSD:EXNESS"


def _child(
    *,
    subscriptions: dict | None = None,
    last_tick_at: datetime | None = None,
    connected: bool = True,
) -> MagicMock:
    child = MagicMock()
    child.subscribe = AsyncMock(return_value="sub-key")
    child.unsubscribe = AsyncMock()
    child.connect = AsyncMock()
    child.disconnect = AsyncMock()
    child.subscriptions = subscriptions or {}
    child.subscription_count = len(subscriptions or {})
    child.last_tick_at = last_tick_at
    child.is_connected = MagicMock(return_value=connected)
    return child


def _adapter(providers: dict) -> RoutingRealtimeQuoteAdapter:
    return RoutingRealtimeQuoteAdapter(providers=providers)


@pytest.mark.asyncio
async def test_subscribe_uses_only_the_provider_the_suffix_names() -> None:
    binance = _child()
    exness = _child()

    key = await _adapter({"binance": binance, "exness": exness}).subscribe(SYMBOL, lambda _: None)

    assert key == "sub-key"
    exness.subscribe.assert_awaited_once()
    binance.subscribe.assert_not_awaited()


# The owner is deliberately not the first-registered child, so delegating to whichever child
# comes first would fail.
@pytest.mark.asyncio
async def test_unsubscribe_reaches_the_owning_provider() -> None:
    first_registered = _child()
    owner = _child()
    adapter = _adapter({"exness": first_registered, "binance": owner})

    await adapter.subscribe("BTCUSDT:BINANCE", lambda _: None)
    await adapter.unsubscribe("BTCUSDT:BINANCE")

    owner.unsubscribe.assert_awaited_once_with("BTCUSDT:BINANCE")
    first_registered.unsubscribe.assert_not_awaited()


# Reconcile can ask to drop a symbol this adapter never subscribed.
@pytest.mark.asyncio
async def test_unsubscribing_an_unknown_symbol_reaches_no_child() -> None:
    child = _child()

    await _adapter({"exness": child}).unsubscribe("NEVER:SUBSCRIBED")

    child.unsubscribe.assert_not_awaited()


# WsSubscriptionAppService._reconcile diffs against these keys; a child missing from the
# merged view would be resubscribed every tick.
@pytest.mark.asyncio
async def test_subscriptions_merges_children() -> None:
    adapter = _adapter(
        {
            "exness": _child(subscriptions={"XAUUSD:EXNESS": ("k1", None)}),
            "binance": _child(subscriptions={"BTCUSDT:BINANCE": ("k2", None)}),
        }
    )

    assert set(adapter.subscriptions.keys()) == {"XAUUSD:EXNESS", "BTCUSDT:BINANCE"}
    assert adapter.subscription_count == 2


@pytest.mark.asyncio
async def test_last_tick_at_is_the_max_across_children() -> None:
    older = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
    newer = datetime(2026, 5, 5, 12, 5, tzinfo=UTC)
    adapter = _adapter(
        {
            "exness": _child(last_tick_at=older),
            "binance": _child(last_tick_at=newer),
        }
    )

    assert adapter.last_tick_at == newer


# A silent child reports None, and max over it would raise.
@pytest.mark.asyncio
async def test_last_tick_at_ignores_a_child_that_has_never_ticked() -> None:
    seen = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
    adapter = _adapter({"exness": _child(last_tick_at=None), "binance": _child(last_tick_at=seen)})

    assert adapter.last_tick_at == seen
    assert _adapter({"exness": _child(last_tick_at=None)}).last_tick_at is None


# Returning a key would make reconcile believe a feed exists.
@pytest.mark.asyncio
async def test_an_unknown_suffix_raises_rather_than_silently_not_subscribing() -> None:
    child = _child()

    with pytest.raises(UnknownDataProviderError, match="No realtime provider registered"):
        await _adapter({"binance": child}).subscribe("XAUUSD:EXNESS", lambda _: None)

    child.subscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_bad_child_does_not_block_shutdown_of_the_others() -> None:
    failing = _child()
    failing.disconnect = AsyncMock(side_effect=RuntimeError("socket stuck"))
    healthy = _child()

    await _adapter({"exness": failing, "binance": healthy}).disconnect()

    healthy.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_is_connected_is_true_when_any_child_is() -> None:
    adapter = _adapter({"exness": _child(connected=False), "binance": _child(connected=True)})

    assert adapter.is_connected() is True
    assert _adapter({"exness": _child(connected=False)}).is_connected() is False


# DI resolves this structurally, so a missing member fails only at runtime. issubclass
# cannot be used: the Protocol has non-method members, which makes it an isinstance-only
# runtime check.
@pytest.mark.asyncio
async def test_the_adapter_satisfies_the_realtime_port() -> None:
    adapter = _adapter({"binance": _child()})

    assert isinstance(adapter, IRealtimeQuoteProviderPort)


# Runs until cancelled, like a real WS loop.
class _BlockingChild:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def run_forever(self) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class TestRunForeverSupervisesEveryChild:
    # A real feed's run_forever never returns, so sequential awaits would leave the second
    # provider unstarted; on teardown stop_quote_feed cancels one task and expects every
    # child to wind down behind it.
    @pytest.mark.asyncio
    async def test_children_run_concurrently_and_all_see_the_cancel(self) -> None:
        first, second = _BlockingChild(), _BlockingChild()
        adapter = _adapter({"exness": first, "binance": second})

        task = asyncio.create_task(adapter.run_forever())
        await asyncio.wait_for(
            asyncio.gather(first.started.wait(), second.started.wait()), timeout=1
        )

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert first.cancelled and second.cancelled
        assert task.cancelled(), "CancelledError must propagate, not be swallowed"
