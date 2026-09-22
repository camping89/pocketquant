"""Realtime routing: one owner per symbol, a merged view for reconcile.

Unlike the REST path there is deliberately no fallback here. Two feeds for one
symbol would both reach BarBuilderDomainService and double-count its ticks,
which is worse than a missing feed because nothing reports it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import (
    RoutingRealtimeQuoteAdapter,
)
from tests.core_test.infra.market_data.conftest import build_settings, lookup_returning

SYMBOL = "ES1!:CME_MINI"
PROVIDERS = {AssetClass.INDEX_FUTURE: ["tradingview", "binance"]}


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


def _adapter(
    providers: dict,
    overrides: dict[str, list[str]] | None = None,
) -> RoutingRealtimeQuoteAdapter:
    return RoutingRealtimeQuoteAdapter(
        providers=providers,
        settings=build_settings(PROVIDERS, overrides),
        symbol_lookup=lookup_returning(AssetClass.INDEX_FUTURE),
    )


@pytest.mark.asyncio
async def test_subscribe_uses_only_the_first_provider() -> None:
    primary = _child()
    secondary = _child()

    key = await _adapter({"tradingview": primary, "binance": secondary}).subscribe(
        SYMBOL, lambda _: None
    )

    assert key == "sub-key"
    primary.subscribe.assert_awaited_once()
    secondary.subscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsubscribe_reaches_the_owning_provider() -> None:
    """The owner is deliberately not the first-registered child.

    With the owner registered first, delegating to "whichever child comes
    first" would pass this while ignoring the recorded owner entirely.
    """
    first_registered = _child()
    owner = _child()
    adapter = _adapter(
        {"tradingview": first_registered, "binance": owner},
        overrides={SYMBOL: ["binance"]},
    )

    await adapter.subscribe(SYMBOL, lambda _: None)
    await adapter.unsubscribe(SYMBOL)

    owner.unsubscribe.assert_awaited_once_with(SYMBOL)
    first_registered.unsubscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsubscribing_an_unknown_symbol_reaches_no_child() -> None:
    """Reconcile can ask to drop a symbol this adapter never subscribed."""
    child = _child()

    await _adapter({"tradingview": child}).unsubscribe("NEVER:SUBSCRIBED")

    child.unsubscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscriptions_merges_children() -> None:
    """``WsSubscriptionAppService._reconcile`` diffs against these keys.

    A child missing from the merged view would be resubscribed every tick.
    """
    adapter = _adapter(
        {
            "tradingview": _child(subscriptions={"ES1!:CME_MINI": ("k1", None)}),
            "binance": _child(subscriptions={"BTCUSDT:BINANCE": ("k2", None)}),
        }
    )

    assert set(adapter.subscriptions.keys()) == {"ES1!:CME_MINI", "BTCUSDT:BINANCE"}
    assert adapter.subscription_count == 2


@pytest.mark.asyncio
async def test_last_tick_at_is_the_max_across_children() -> None:
    older = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
    newer = datetime(2026, 5, 5, 12, 5, tzinfo=UTC)
    adapter = _adapter(
        {
            "tradingview": _child(last_tick_at=older),
            "binance": _child(last_tick_at=newer),
        }
    )

    assert adapter.last_tick_at == newer


@pytest.mark.asyncio
async def test_last_tick_at_ignores_a_child_that_has_never_ticked() -> None:
    """A silent child reports ``None``; ``max`` over it would raise."""
    seen = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
    adapter = _adapter(
        {"tradingview": _child(last_tick_at=None), "binance": _child(last_tick_at=seen)}
    )

    assert adapter.last_tick_at == seen
    assert _adapter({"tradingview": _child(last_tick_at=None)}).last_tick_at is None


@pytest.mark.asyncio
async def test_an_unroutable_symbol_raises_rather_than_silently_not_subscribing() -> None:
    """The resolved provider is not registered — reconcile must see a failure.

    Returning a key would make the caller believe a feed exists. Phase 6 gives
    index futures a polling quote adapter; until it is registered this is the
    state a tracked futures symbol lands in.
    """
    adapter = _adapter({"binance": _child()}, overrides={SYMBOL: ["nowhere"]})

    with pytest.raises(ValueError, match="No realtime provider registered"):
        await adapter.subscribe(SYMBOL, lambda _: None)


@pytest.mark.asyncio
async def test_one_bad_child_does_not_block_shutdown_of_the_others() -> None:
    failing = _child()
    failing.disconnect = AsyncMock(side_effect=RuntimeError("socket stuck"))
    healthy = _child()

    await _adapter({"tradingview": failing, "binance": healthy}).disconnect()

    healthy.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_is_connected_is_true_when_any_child_is() -> None:
    adapter = _adapter(
        {"tradingview": _child(connected=False), "binance": _child(connected=True)}
    )

    assert adapter.is_connected() is True
    assert _adapter({"tradingview": _child(connected=False)}).is_connected() is False


@pytest.mark.asyncio
async def test_the_adapter_satisfies_the_realtime_port() -> None:
    """DI resolves this structurally; a missing member fails only at runtime.

    ``issubclass`` cannot be used: the Protocol has non-method members, which
    makes it an isinstance-only runtime check.
    """
    adapter = _adapter({"binance": _child()})

    assert isinstance(adapter, IRealtimeQuoteProviderPort)


class _BlockingChild:
    """A child whose feed runs until cancelled, like a real WS loop."""

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
    """Children must run concurrently, and cancellation must reach all of them."""

    @pytest.mark.asyncio
    async def test_children_run_concurrently_and_all_see_the_cancel(self) -> None:
        """Sequential awaits would strand every child after the first.

        A real feed's ``run_forever`` never returns, so awaiting them in turn
        would leave the second provider permanently unstarted — and on
        teardown ``stop_quote_feed`` cancels one task and expects every child
        to wind down behind it.
        """
        first, second = _BlockingChild(), _BlockingChild()
        adapter = _adapter({"tradingview": first, "binance": second})

        task = asyncio.create_task(adapter.run_forever())
        await asyncio.wait_for(
            asyncio.gather(first.started.wait(), second.started.wait()), timeout=1
        )

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert first.cancelled and second.cancelled
        assert task.cancelled(), "CancelledError must propagate, not be swallowed"
