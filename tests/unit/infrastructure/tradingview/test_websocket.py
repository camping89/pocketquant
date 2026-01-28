"""Unit tests for TradingView WebSocket provider."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets import State

from src.infrastructure.tradingview.websocket import (
    TradingViewWebSocketProvider,
    _create_message,
    _generate_session_id,
    _parse_messages,
)


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_generate_session_id_format(self):
        """Session ID should have format: prefix_12chars."""
        session_id = _generate_session_id("qs")

        assert session_id.startswith("qs_")
        assert len(session_id) == 15  # "qs_" + 12 chars

    def test_generate_session_id_custom_prefix(self):
        """Custom prefix should be used."""
        session_id = _generate_session_id("custom")

        assert session_id.startswith("custom_")

    def test_generate_session_id_unique(self):
        """Each call should generate unique ID."""
        ids = {_generate_session_id() for _ in range(100)}
        assert len(ids) == 100

    def test_create_message_format(self):
        """Message should follow TradingView protocol: ~m~{len}~m~{json}."""
        msg = _create_message("test_method", ["param1", "param2"])

        assert msg.startswith("~m~")
        assert "~m~" in msg[3:]

        # Extract JSON part
        parts = msg.split("~m~")
        json_part = parts[2]
        data = json.loads(json_part)

        assert data["m"] == "test_method"
        assert data["p"] == ["param1", "param2"]

    def test_create_message_length_correct(self):
        """Length prefix should match actual JSON length."""
        msg = _create_message("method", [])

        parts = msg.split("~m~")
        length = int(parts[1])
        json_part = parts[2]

        assert length == len(json_part)

    def test_parse_messages_single(self):
        """Parse single message."""
        raw = '~m~42~m~{"m":"qsd","p":["session",{"n":"AAPL"}]}'
        messages = _parse_messages(raw)

        assert len(messages) == 1
        assert messages[0]["m"] == "qsd"

    def test_parse_messages_multiple(self):
        """Parse multiple messages in one frame."""
        msg1 = '{"m":"msg1","p":[]}'
        msg2 = '{"m":"msg2","p":[]}'
        raw = f"~m~{len(msg1)}~m~{msg1}~m~{len(msg2)}~m~{msg2}"

        messages = _parse_messages(raw)

        assert len(messages) == 2
        assert messages[0]["m"] == "msg1"
        assert messages[1]["m"] == "msg2"

    def test_parse_messages_skip_heartbeat(self):
        """Heartbeat messages (~h~) should be skipped."""
        raw = "~m~3~m~~h~1"
        messages = _parse_messages(raw)

        assert len(messages) == 0

    def test_parse_messages_skip_invalid_json(self):
        """Invalid JSON should be skipped silently."""
        raw = "~m~10~m~not valid json"
        messages = _parse_messages(raw)

        assert len(messages) == 0

    def test_parse_messages_empty(self):
        """Empty string returns empty list."""
        messages = _parse_messages("")
        assert messages == []


class TestTradingViewWebSocketProvider:
    """Tests for TradingViewWebSocketProvider class."""

    def test_init_defaults(self):
        """Provider initializes with correct defaults."""
        provider = TradingViewWebSocketProvider()

        assert provider._auth_token is None
        assert provider._ws is None
        assert provider._session_id == ""
        assert provider._subscriptions == {}
        assert provider._running is False
        assert provider._reconnect_delay == 1.0
        assert provider._max_reconnect_delay == 60.0

    def test_init_with_auth_token(self):
        """Auth token should be stored."""
        provider = TradingViewWebSocketProvider(auth_token="test_token")
        assert provider._auth_token == "test_token"

    def test_is_connected_false_when_no_ws(self):
        """is_connected returns False when ws is None."""
        provider = TradingViewWebSocketProvider()
        assert provider.is_connected() is False

    def test_is_connected_false_when_ws_closed(self):
        """is_connected returns False when ws state is not OPEN."""
        provider = TradingViewWebSocketProvider()
        provider._ws = MagicMock()
        provider._ws.state = State.CLOSED

        assert provider.is_connected() is False

    def test_is_connected_true_when_ws_open(self):
        """is_connected returns True when ws state is OPEN."""
        provider = TradingViewWebSocketProvider()
        provider._ws = MagicMock()
        provider._ws.state = State.OPEN

        assert provider.is_connected() is True

    def test_subscription_count(self):
        """subscription_count returns number of subscriptions."""
        provider = TradingViewWebSocketProvider()

        assert provider.subscription_count == 0

        provider._subscriptions["NASDAQ:AAPL"] = lambda x: None
        assert provider.subscription_count == 1

        provider._subscriptions["NYSE:TSLA"] = lambda x: None
        assert provider.subscription_count == 2

    @pytest.mark.asyncio
    async def test_connect_creates_session(self):
        """connect() should establish connection and create session."""
        provider = TradingViewWebSocketProvider()

        mock_ws = AsyncMock()

        async def mock_connect(*args, **kwargs):
            return mock_ws

        with patch("src.infrastructure.tradingview.websocket.websockets.connect", side_effect=mock_connect):
            await provider.connect()

        assert provider._ws == mock_ws
        assert provider._session_id.startswith("qs_")
        assert provider._reconnect_delay == 1.0

        # Should send quote_create_session and quote_set_fields
        assert mock_ws.send.call_count == 2

    @pytest.mark.asyncio
    async def test_disconnect_closes_connection(self):
        """disconnect() should close ws and reset state."""
        provider = TradingViewWebSocketProvider()
        provider._ws = AsyncMock()
        provider._running = True

        await provider.disconnect()

        assert provider._running is False
        assert provider._ws is None

    @pytest.mark.asyncio
    async def test_subscribe_without_connection_raises(self):
        """subscribe() without connection should raise RuntimeError."""
        provider = TradingViewWebSocketProvider()

        with pytest.raises(RuntimeError, match="WebSocket not connected"):
            await provider.subscribe("AAPL", "NASDAQ", lambda x: None)

    @pytest.mark.asyncio
    async def test_subscribe_adds_to_subscriptions(self):
        """subscribe() should add callback and send message."""
        provider = TradingViewWebSocketProvider()
        provider._ws = AsyncMock()
        provider._session_id = "test_session"

        callback = lambda x: None
        symbol_key = await provider.subscribe("AAPL", "NASDAQ", callback)

        assert symbol_key == "NASDAQ:AAPL"
        assert provider._subscriptions["NASDAQ:AAPL"] == callback
        provider._ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_uppercase_symbol_key(self):
        """Symbol key should be uppercase."""
        provider = TradingViewWebSocketProvider()
        provider._ws = AsyncMock()
        provider._session_id = "test_session"

        symbol_key = await provider.subscribe("aapl", "nasdaq", lambda x: None)

        assert symbol_key == "NASDAQ:AAPL"

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscription(self):
        """unsubscribe() should remove from dict and send message."""
        provider = TradingViewWebSocketProvider()
        provider._ws = AsyncMock()
        provider._session_id = "test_session"
        provider._subscriptions["NASDAQ:AAPL"] = lambda x: None

        await provider.unsubscribe("AAPL", "NASDAQ")

        assert "NASDAQ:AAPL" not in provider._subscriptions
        provider._ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_does_nothing(self):
        """unsubscribe() for non-existent symbol does nothing."""
        provider = TradingViewWebSocketProvider()
        provider._ws = AsyncMock()

        await provider.unsubscribe("AAPL", "NASDAQ")

        provider._ws.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_unsubscribe_without_connection_returns(self):
        """unsubscribe() without connection should return silently."""
        provider = TradingViewWebSocketProvider()

        # Should not raise
        await provider.unsubscribe("AAPL", "NASDAQ")

    @pytest.mark.asyncio
    async def test_handle_quote_update_calls_callback(self):
        """Quote update should trigger callback with mapped data."""
        provider = TradingViewWebSocketProvider()
        provider._session_id = "test_session"

        received = []
        provider._subscriptions["NASDAQ:AAPL"] = lambda x: received.append(x)

        params = [
            "test_session",
            {
                "n": "NASDAQ:AAPL",
                "v": {
                    "lp": 150.50,
                    "volume": 1000000,
                    "bid": 150.49,
                    "ask": 150.51,
                },
            },
        ]

        await provider._handle_quote_update(params)

        assert len(received) == 1
        assert received[0]["symbol_key"] == "NASDAQ:AAPL"
        assert received[0]["last_price"] == 150.50
        assert received[0]["volume"] == 1000000

    @pytest.mark.asyncio
    async def test_handle_quote_update_async_callback(self):
        """Async callbacks should be awaited."""
        provider = TradingViewWebSocketProvider()
        provider._session_id = "test_session"

        received = []

        async def async_callback(data):
            received.append(data)

        provider._subscriptions["NASDAQ:AAPL"] = async_callback

        params = [
            "test_session",
            {"n": "NASDAQ:AAPL", "v": {"lp": 100}},
        ]

        await provider._handle_quote_update(params)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_handle_quote_update_wrong_session_ignored(self):
        """Quote updates for wrong session should be ignored."""
        provider = TradingViewWebSocketProvider()
        provider._session_id = "my_session"

        received = []
        provider._subscriptions["NASDAQ:AAPL"] = lambda x: received.append(x)

        params = [
            "other_session",  # Wrong session
            {"n": "NASDAQ:AAPL", "v": {"lp": 100}},
        ]

        await provider._handle_quote_update(params)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_handle_quote_update_callback_exception_logged(self):
        """Callback exceptions should be caught and logged."""
        provider = TradingViewWebSocketProvider()
        provider._session_id = "test_session"

        def bad_callback(data):
            raise ValueError("Test error")

        provider._subscriptions["NASDAQ:AAPL"] = bad_callback

        params = [
            "test_session",
            {"n": "NASDAQ:AAPL", "v": {"lp": 100}},
        ]

        # Should not raise
        await provider._handle_quote_update(params)

    @pytest.mark.asyncio
    async def test_send_heartbeat(self):
        """Heartbeat should send ~h~1."""
        provider = TradingViewWebSocketProvider()
        provider._ws = AsyncMock()

        await provider._send_heartbeat()

        provider._ws.send.assert_called_once_with("~h~1")

    @pytest.mark.asyncio
    async def test_send_heartbeat_no_connection(self):
        """Heartbeat without connection should do nothing."""
        provider = TradingViewWebSocketProvider()

        # Should not raise
        await provider._send_heartbeat()
