"""Unit tests for BinanceWebSocketClient @aggTrade stream.

Feeds canned aggTrade frames directly into _handle_frame — no real WS connection.
Covers: callback dispatch, volume delta semantics, reconnect backoff, sub/unsub counts.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pocketquant.core.infrastructure.binance.binance_websocket_client import (
    _RECONNECT_DELAY_INITIAL,
    _RECONNECT_DELAY_MAX,
    BinanceWebSocketClient,
)

_WS_MODULE = "pocketquant.core.infrastructure.binance.binance_websocket_client"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _aggtrade_frame(
    symbol: str = "BTCUSDT",
    price: str = "50000.00",
    qty: str = "0.01",
    trade_time_ms: int = 1_700_000_000_000,
    agg_id: int = 1,
) -> str:
    """Build a canned @aggTrade JSON frame (single-stream format)."""
    return json.dumps({
        "e": "aggTrade",
        "E": trade_time_ms + 1,
        "s": symbol,
        "a": agg_id,
        "p": price,
        "q": qty,
        "f": agg_id,
        "l": agg_id,
        "T": trade_time_ms,
        "m": True,
        "M": True,
    })


def _combined_frame(inner: dict) -> str:
    """Wrap an aggTrade event in combined-stream envelope."""
    return json.dumps({"stream": f"{inner['s'].lower()}@aggTrade", "data": inner})


# ---------------------------------------------------------------------------
# aggTrade frame parsing + callback dispatch
# ---------------------------------------------------------------------------

class TestAggTradeFrameParsing:
    """Tests for _handle_frame parsing and callback invocation."""

    @pytest.mark.asyncio
    async def test_single_aggtrade_callback_volume_is_delta(self):
        """Callback receives volume == raw q (per-trade delta, not cumulative)."""
        client = BinanceWebSocketClient()
        received: list[dict] = []

        await client.subscribe("BTCUSDT:BINANCE", lambda d: received.append(d))
        await client._handle_frame(_aggtrade_frame(qty="0.01"))

        assert len(received) == 1
        assert received[0]["volume"] == pytest.approx(0.01)

    @pytest.mark.asyncio
    async def test_aggtrade_callback_last_price(self):
        """Callback receives last_price == float(p)."""
        client = BinanceWebSocketClient()
        received: list[dict] = []

        await client.subscribe("BTCUSDT:BINANCE", lambda d: received.append(d))
        await client._handle_frame(_aggtrade_frame(price="50000.00"))

        assert received[0]["last_price"] == pytest.approx(50_000.0)

    @pytest.mark.asyncio
    async def test_aggtrade_callback_timestamp_matches_trade_time(self):
        """Callback timestamp corresponds to aggTrade's T field (trade time ms)."""
        ts_ms = 1_700_000_000_000
        client = BinanceWebSocketClient()
        received: list[dict] = []

        await client.subscribe("BTCUSDT:BINANCE", lambda d: received.append(d))
        await client._handle_frame(_aggtrade_frame(trade_time_ms=ts_ms))

        expected_dt = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
        assert received[0]["timestamp"] == expected_dt

    @pytest.mark.asyncio
    async def test_two_consecutive_frames_produce_delta_not_cumulative(self):
        """Two frames q=0.5 then q=0.3 → callbacks get 0.5 then 0.3 (NOT 0.5, 0.8)."""
        client = BinanceWebSocketClient()
        volumes: list[float] = []

        await client.subscribe("BTCUSDT:BINANCE", lambda d: volumes.append(d["volume"]))
        await client._handle_frame(_aggtrade_frame(qty="0.5", agg_id=1))
        await client._handle_frame(_aggtrade_frame(qty="0.3", agg_id=2))

        assert len(volumes) == 2
        assert volumes[0] == pytest.approx(0.5)
        assert volumes[1] == pytest.approx(0.3)  # NOT 0.8

    @pytest.mark.asyncio
    async def test_combined_stream_frame_dispatched_correctly(self):
        """Combined-stream envelope (data key) is unwrapped before dispatch."""
        client = BinanceWebSocketClient()
        received: list[dict] = []

        await client.subscribe("BTCUSDT:BINANCE", lambda d: received.append(d))
        inner = json.loads(_aggtrade_frame(qty="0.05"))
        await client._handle_frame(_combined_frame(inner))

        assert len(received) == 1
        assert received[0]["volume"] == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_non_aggtrade_event_ignored(self):
        """Frames with e != 'aggTrade' do not trigger callbacks."""
        client = BinanceWebSocketClient()
        received: list[dict] = []

        await client.subscribe("BTCUSDT:BINANCE", lambda d: received.append(d))
        other_event = json.dumps({"e": "trade", "s": "BTCUSDT", "p": "50000", "q": "0.1"})
        await client._handle_frame(other_event)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_async_callback_awaited(self):
        """Async callbacks are awaited, not fire-and-forget."""
        client = BinanceWebSocketClient()
        received: list[dict] = []

        async def async_cb(d: dict) -> None:
            received.append(d)

        await client.subscribe("BTCUSDT:BINANCE", async_cb)
        await client._handle_frame(_aggtrade_frame())

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_last_tick_at_updated_on_aggtrade(self):
        """last_tick_at is set to a datetime on first aggTrade received."""
        client = BinanceWebSocketClient()
        assert client.last_tick_at is None

        await client.subscribe("BTCUSDT:BINANCE", lambda _: None)
        await client._handle_frame(_aggtrade_frame())

        assert client.last_tick_at is not None
        assert isinstance(client.last_tick_at, datetime)


# ---------------------------------------------------------------------------
# Subscribe / Unsubscribe
# ---------------------------------------------------------------------------

class TestSubscriptionManagement:
    """Tests for subscription count tracking."""

    @pytest.mark.asyncio
    async def test_subscribe_increments_count(self):
        client = BinanceWebSocketClient()
        assert client.subscription_count == 0

        await client.subscribe("BTCUSDT:BINANCE", lambda _: None)
        assert client.subscription_count == 1

        await client.subscribe("ETHUSDT:BINANCE", lambda _: None)
        assert client.subscription_count == 2

    @pytest.mark.asyncio
    async def test_unsubscribe_decrements_count(self):
        client = BinanceWebSocketClient()
        await client.subscribe("BTCUSDT:BINANCE", lambda _: None)
        await client.subscribe("ETHUSDT:BINANCE", lambda _: None)
        assert client.subscription_count == 2

        await client.unsubscribe("BTCUSDT:BINANCE")
        assert client.subscription_count == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_no_error(self):
        client = BinanceWebSocketClient()
        # Should not raise
        await client.unsubscribe("BTCUSDT:BINANCE")
        assert client.subscription_count == 0

    @pytest.mark.asyncio
    async def test_subscribe_returns_symbol_key(self):
        client = BinanceWebSocketClient()
        key = await client.subscribe("BTCUSDT:BINANCE", lambda _: None)
        assert key == "BTCUSDT:BINANCE"


# ---------------------------------------------------------------------------
# Reconnect backoff
# ---------------------------------------------------------------------------

class TestReconnectBackoff:
    """Tests for exponential backoff behaviour in run_forever."""

    @pytest.mark.asyncio
    async def test_backoff_doubles_each_failure(self):
        """_backoff_sleep doubles _reconnect_delay on each call."""
        client = BinanceWebSocketClient()
        assert client._reconnect_delay == _RECONNECT_DELAY_INITIAL  # 1.0

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await client._backoff_sleep()
            assert client._reconnect_delay == 2.0

            await client._backoff_sleep()
            assert client._reconnect_delay == 4.0

            await client._backoff_sleep()
            assert client._reconnect_delay == 8.0

    @pytest.mark.asyncio
    async def test_backoff_capped_at_max(self):
        """Backoff delay is capped at _RECONNECT_DELAY_MAX (60s)."""
        client = BinanceWebSocketClient()
        client._reconnect_delay = 32.0  # near cap

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await client._backoff_sleep()
            assert client._reconnect_delay == _RECONNECT_DELAY_MAX  # 64 → capped at 60

    @pytest.mark.asyncio
    async def test_backoff_never_exceeds_max(self):
        """Multiple backoff calls never push delay above max."""
        client = BinanceWebSocketClient()
        with patch("asyncio.sleep", new_callable=AsyncMock):
            for _ in range(20):
                await client._backoff_sleep()
        assert client._reconnect_delay == _RECONNECT_DELAY_MAX

    @pytest.mark.asyncio
    async def test_connect_resets_backoff(self):
        """Successful connect() resets _reconnect_delay to initial value."""
        client = BinanceWebSocketClient()
        client._reconnect_delay = 32.0

        mock_ws = MagicMock()

        # websockets.connect() returns an object with __await__; wrap as coroutine
        async def _fake_connect(*args, **kwargs):
            return mock_ws

        ws_module = "pocketquant.core.infrastructure.binance.binance_websocket_client"
        with patch(f"{ws_module}.websockets.connect", side_effect=_fake_connect):
            await client.subscribe("BTCUSDT:BINANCE", lambda _: None)
            await client.connect()

        assert client._reconnect_delay == _RECONNECT_DELAY_INITIAL

    @pytest.mark.asyncio
    async def test_run_forever_reconnects_on_connection_closed(self):
        """run_forever sleeps after ConnectionClosed then reconnects."""
        import websockets as _ws

        client = BinanceWebSocketClient()
        await client.subscribe("BTCUSDT:BINANCE", lambda _: None)

        connect_count = 0
        sleep_delays: list[float] = []

        async def _mock_connect(*args, **kwargs):
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                # First WS: async iterator immediately raises ConnectionClosed
                async def _bad_iter():
                    raise _ws.ConnectionClosed(None, None)  # type: ignore[arg-type]
                    yield  # pragma: no cover — makes this an async generator

                mock_ws = MagicMock()
                mock_ws.__aiter__ = lambda self: _bad_iter()
                mock_ws.close = AsyncMock()
                return mock_ws
            # Second connect: stop the loop so test doesn't hang
            client._running = False
            # Return a mock WS that terminates immediately
            async def _empty_iter():
                return
                yield  # pragma: no cover — async generator sentinel

            mock_ws2 = MagicMock()
            mock_ws2.__aiter__ = lambda self: _empty_iter()
            mock_ws2.close = AsyncMock()
            return mock_ws2

        async def _mock_sleep(delay: float) -> None:
            sleep_delays.append(delay)

        with (
            patch(f"{_WS_MODULE}.websockets.connect", side_effect=_mock_connect),
            patch(f"{_WS_MODULE}.asyncio.sleep", side_effect=_mock_sleep),
        ):
            await client.run_forever()

        assert connect_count == 2
        # Only backoff sleep is recorded (watchdog cancelled before its first await runs).
        backoff_delays = [d for d in sleep_delays if d == _RECONNECT_DELAY_INITIAL]
        assert len(backoff_delays) == 1


# ---------------------------------------------------------------------------
# Silent exit + watchdog (regression: websockets 16.0 + Python 3.14)
# ---------------------------------------------------------------------------


class TestSilentExitAndWatchdog:
    """Tests for silent-exit handling and stale-socket watchdog."""

    @pytest.mark.asyncio
    async def test_silent_iterator_exit_triggers_reconnect(self):
        """When `async for` exits silently (close 1000/1001), run_forever reconnects."""
        client = BinanceWebSocketClient()
        await client.subscribe("BTCUSDT:BINANCE", lambda _: None)

        connect_count = 0
        backoff_calls: list[float] = []

        async def _mock_connect(*args, **kwargs):
            nonlocal connect_count
            connect_count += 1

            async def _empty_iter():
                # Silent exit — websockets behavior for close codes 1000/1001
                return
                yield  # pragma: no cover

            mock_ws = MagicMock()
            mock_ws.__aiter__ = lambda self: _empty_iter()
            mock_ws.close = AsyncMock()
            if connect_count >= 2:
                # Stop after second silent exit so the test terminates
                client._running = False
            return mock_ws

        async def _mock_backoff(self):
            backoff_calls.append(self._reconnect_delay)

        with (
            patch(f"{_WS_MODULE}.websockets.connect", side_effect=_mock_connect),
            patch.object(BinanceWebSocketClient, "_backoff_sleep", _mock_backoff),
        ):
            await client.run_forever()

        # Two connects: first silent-exit triggers reconnect, second sets _running=False
        assert connect_count == 2
        # Backoff invoked once after the first silent exit
        assert len(backoff_calls) == 1

    @pytest.mark.asyncio
    async def test_watchdog_force_closes_stale_socket(self):
        """Watchdog calls _close_ws when last_tick_at lags beyond timeout."""
        client = BinanceWebSocketClient()
        client._ws = MagicMock()
        client._ws.close = AsyncMock()
        # Force lag > threshold by backdating last_tick_at
        client.last_tick_at = datetime(2000, 1, 1, tzinfo=UTC)

        # Patch sleep so the watchdog wakes up immediately
        with patch(f"{_WS_MODULE}.asyncio.sleep", new_callable=AsyncMock):
            await client._stale_connection_watchdog()

        # _close_ws was invoked — ws closed and reference cleared
        assert client._ws is None

    @pytest.mark.asyncio
    async def test_watchdog_skips_when_last_tick_is_none(self):
        """Watchdog must not trip before any tick arrives — avoids killing fresh connection."""
        client = BinanceWebSocketClient()
        client._ws = MagicMock()
        client._ws.close = AsyncMock()
        client.last_tick_at = None

        sleeps = 0

        async def _mock_sleep(_delay: float) -> None:
            nonlocal sleeps
            sleeps += 1
            if sleeps >= 3:
                # Break the watchdog loop by setting last_tick_at to recent
                client.last_tick_at = datetime.now(UTC)
                # Then backdate to trigger close on next iteration
                client.last_tick_at = datetime(2000, 1, 1, tzinfo=UTC)

        with patch(f"{_WS_MODULE}.asyncio.sleep", side_effect=_mock_sleep):
            await client._stale_connection_watchdog()

        # Watchdog tolerated None for 3 ticks before tripping
        assert sleeps >= 3
        assert client._ws is None
