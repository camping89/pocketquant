"""TradingViewQuoteAdapter: a polling quote source that is quiet while closed.

Polls are driven one at a time through ``_poll_once`` so no test waits on the
poll interval; the task lifecycle is exercised through subscribe/unsubscribe.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.binance.binance_mappers import aggtrade_to_quote_dict
from pocketquant.core.infra.tradingview.tradingview_client_interface import RawBar
from pocketquant.core.infra.tradingview.tradingview_quote_adapter import TradingViewQuoteAdapter

ES = "ES1!:CME_MINI"
MINUTE = datetime(2026, 9, 23, 14, 30, tzinfo=UTC).timestamp()


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.bars: list[RawBar] = []
        self.error: Exception | None = None

    async def fetch_bars(self, **kwargs: Any) -> list[RawBar]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return list(self.bars)

    def is_authenticated(self) -> bool:
        return False  # anonymous, as production runs


class _StubCalendar:
    def __init__(self, open_: bool) -> None:
        self.open = open_

    def is_open(self, instant: datetime) -> bool:
        return self.open


class _StubCalendars:
    def __init__(self, calendar: _StubCalendar) -> None:
        self._calendar = calendar

    async def for_symbol(self, composite: str) -> _StubCalendar:
        return self._calendar


def _bar(close: float, volume: float, epoch: float = MINUTE) -> RawBar:
    return RawBar(
        epoch_seconds=epoch, open=close, high=close, low=close, close=close, volume=volume
    )


def _adapter(
    open_: bool = True, **settings: Any
) -> tuple[TradingViewQuoteAdapter, _FakeClient, list[dict[str, Any]]]:
    client = _FakeClient()
    adapter = TradingViewQuoteAdapter(
        client=client,
        settings=Settings(**settings),
        calendar_factory=_StubCalendars(_StubCalendar(open_)),  # type: ignore[arg-type]
    )
    quotes: list[dict[str, Any]] = []
    adapter._subscriptions[ES] = quotes.append
    return adapter, client, quotes


@pytest.mark.asyncio
async def test_closed_market_makes_no_client_call() -> None:
    adapter, client, quotes = _adapter(open_=False)
    client.bars = [_bar(4500.0, 10.0)]

    await adapter._poll_once(ES)

    assert client.calls == []
    assert quotes == []


@pytest.mark.asyncio
async def test_open_market_emits_quote_on_price_change() -> None:
    adapter, client, quotes = _adapter()
    client.bars = [_bar(4499.75, 4.0, MINUTE - 60), _bar(4500.0, 10.0)]

    await adapter._poll_once(ES)
    client.bars = [_bar(4500.25, 16.0)]
    await adapter._poll_once(ES)

    assert [(q["last_price"], q["volume"]) for q in quotes] == [(4500.0, 10.0), (4500.25, 6.0)]
    assert quotes[0]["timestamp"] == datetime.fromtimestamp(MINUTE, tz=UTC)
    assert client.calls[0] == {
        "code": "ES",
        "exchange": "CME_MINI",
        "interval": client.calls[0]["interval"],
        "n_bars": 2,
        "fut_contract": 1,
    }
    assert adapter.last_tick_at is not None


@pytest.mark.asyncio
async def test_unchanged_close_emits_nothing() -> None:
    adapter, client, quotes = _adapter()
    client.bars = [_bar(4500.0, 10.0)]
    await adapter._poll_once(ES)

    client.bars = [_bar(4500.0, 14.0)]
    await adapter._poll_once(ES)
    assert len(quotes) == 1

    # The skipped poll's volume is carried into the next emission, not lost.
    client.bars = [_bar(4500.5, 15.0)]
    await adapter._poll_once(ES)
    assert quotes[-1]["volume"] == 5.0


@pytest.mark.asyncio
async def test_quote_dict_matches_the_binance_key_set() -> None:
    adapter, client, quotes = _adapter()
    client.bars = [_bar(4500.0, 10.0)]

    await adapter._poll_once(ES)

    binance = aggtrade_to_quote_dict({"T": 1_700_000_000_000, "p": "1", "q": "1"}, "BTCUSDT")
    assert set(quotes[0]) == set(binance)
    assert quotes[0]["symbol"] == ES


@pytest.mark.asyncio
async def test_unsubscribe_cancels_the_poll_task() -> None:
    adapter, _, _ = _adapter(open_=False)
    del adapter._subscriptions[ES]

    await adapter.subscribe(ES, lambda quote: None)
    task = adapter._tasks[ES]
    await asyncio.sleep(0)
    assert not task.done()

    await adapter.unsubscribe(ES)

    assert task.cancelled()
    assert ES not in adapter._tasks
    assert adapter.subscriptions == {}


@pytest.mark.asyncio
async def test_new_minute_emits_full_bar_volume_and_revisions_clamp_to_zero() -> None:
    adapter, client, quotes = _adapter()
    client.bars = [_bar(4500.0, 10.0)]
    await adapter._poll_once(ES)

    client.bars = [_bar(4500.25, 3.0, MINUTE + 60)]
    await adapter._poll_once(ES)
    client.bars = [_bar(4500.5, 2.0, MINUTE + 60)]
    await adapter._poll_once(ES)

    assert [q["volume"] for q in quotes] == [10.0, 3.0, 0.0]


@pytest.mark.asyncio
async def test_failure_streak_reports_disconnected_until_a_poll_succeeds() -> None:
    adapter, client, _ = _adapter(open_=False)
    del adapter._subscriptions[ES]
    await adapter.subscribe(ES, lambda quote: None)
    adapter._calendar_factory._calendar.open = True  # type: ignore[attr-defined]
    try:
        assert adapter.is_connected()  # anonymous is not disconnected

        client.error = ConnectionError("socket dropped")
        for _ in range(2):
            await adapter._poll_once(ES)
        assert adapter.is_connected()  # one-in-nine drops heal on the next poll
        await adapter._poll_once(ES)
        assert not adapter.is_connected()

        client.error = None
        client.bars = [_bar(4500.0, 1.0)]
        await adapter._poll_once(ES)
        assert adapter.is_connected()
    finally:
        await adapter.disconnect()


def test_poll_interval_never_beats_the_plan_floor() -> None:
    assert _adapter(tradingview_poll_seconds=5)[0].poll_seconds == 60
    assert _adapter(tradingview_poll_seconds=120)[0].poll_seconds == 120
    assert _adapter()[0].poll_seconds == 60


def test_satisfies_the_realtime_port() -> None:
    assert isinstance(_adapter()[0], IRealtimeQuoteProviderPort)


@pytest.mark.asyncio
async def test_a_raising_subscriber_does_not_end_the_feed() -> None:
    adapter, client, _ = _adapter()
    adapter._poll_seconds = 0  # type: ignore[assignment]
    seen: list[float] = []

    def explode(quote: dict[str, Any]) -> None:
        seen.append(quote["last_price"])
        client.bars = [_bar(quote["last_price"] + 0.25, 1.0)]
        raise RuntimeError("subscriber bug")

    adapter._subscriptions[ES] = explode
    client.bars = [_bar(4500.0, 1.0)]
    task = asyncio.create_task(adapter._poll_loop(ES))
    try:
        for _ in range(20):
            await asyncio.sleep(0)
        assert len(seen) >= 2
        assert not task.done()
    finally:
        task.cancel()


@pytest.mark.asyncio
async def test_a_new_minute_at_the_same_price_is_still_emitted() -> None:
    adapter, client, quotes = _adapter()
    client.bars = [_bar(4500.0, 10.0)]
    await adapter._poll_once(ES)

    client.bars = [_bar(4500.0, 4.0, MINUTE + 60)]
    await adapter._poll_once(ES)

    assert [(q["timestamp"].minute, q["volume"]) for q in quotes] == [(30, 10.0), (31, 4.0)]


@pytest.mark.asyncio
async def test_unsubscribe_does_not_swallow_the_callers_cancellation() -> None:
    adapter, _, _ = _adapter(open_=False)
    del adapter._subscriptions[ES]
    await adapter.subscribe(ES, lambda quote: None)
    poll = adapter._tasks[ES]

    # A poll task slow to finish keeps unsubscribe waiting; cancelling the
    # caller there must still end the caller.
    blocker = asyncio.Event()

    async def slow_poll() -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await blocker.wait()
            raise

    poll.cancel()
    adapter._tasks[ES] = asyncio.create_task(slow_poll())
    await asyncio.sleep(0)

    caller = asyncio.create_task(adapter.unsubscribe(ES))
    await asyncio.sleep(0.01)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    blocker.set()
    await asyncio.sleep(0)
