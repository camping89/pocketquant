"""TradingView WebSocket provider for real-time quotes.

This provider connects to TradingView's WebSocket endpoint to receive
real-time quote updates. Based on reverse-engineered protocol from:
- https://github.com/mohamadkhalaj/tradingView-API
- https://github.com/Troodi/TradingViewWebsocket

Protocol notes:
- Connection: wss://data.tradingview.com/socket.io/websocket
- Messages are prefixed with ~m~ and length
- Quote sessions use "qs_" prefix
- Chart sessions use "cs_" prefix
"""

import asyncio
import json
import random
import re
import string
from collections.abc import Callable
from datetime import datetime
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from src.common.logging import get_logger

logger = get_logger(__name__)

# TradingView WebSocket endpoint
WS_URL = "wss://data.tradingview.com/socket.io/websocket"

QUOTE_FIELDS = [
    "lp", "volume", "bid", "ask", "ch", "chp",
    "open_price", "high_price", "low_price", "prev_close_price",
]


def _generate_session_id(prefix: str = "qs") -> str:
    """Generate a random session ID.

    Args:
        prefix: Session prefix (qs for quote, cs for chart).

    Returns:
        Random session ID like "qs_abc123xyz789".
    """
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(random.choices(chars, k=12))
    return f"{prefix}_{random_part}"


def _create_message(method: str, params: list[Any]) -> str:
    """Create a TradingView WebSocket message.

    Args:
        method: Method name (e.g., "quote_create_session").
        params: List of parameters.

    Returns:
        Formatted message string.
    """
    message = json.dumps({"m": method, "p": params})
    return f"~m~{len(message)}~m~{message}"


def _parse_messages(raw_data: str) -> list[dict[str, Any]]:
    """Parse raw WebSocket data into messages.

    Args:
        raw_data: Raw data from WebSocket.

    Returns:
        List of parsed message dictionaries.
    """
    messages = []

    # Split by message delimiter pattern
    pattern = r"~m~\d+~m~"
    parts = re.split(pattern, raw_data)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("~h~"):
            continue
        try:
            data = json.loads(part)
            messages.append(data)
        except json.JSONDecodeError:
            pass

    return messages


class TradingViewWebSocketProvider:
    """Real-time quote provider using TradingView WebSocket.

    Usage:
        provider = TradingViewWebSocketProvider()

        async def on_quote(quote_data):
            print(f"Received: {quote_data}")

        await provider.connect()
        await provider.subscribe("AAPL", "NASDAQ", on_quote)

        # Keep running...
        await provider.run_forever()
    """

    def __init__(self, auth_token: str | None = None):
        """Initialize the WebSocket provider.

        Args:
            auth_token: Optional TradingView auth token for premium data.
        """
        self._auth_token = auth_token
        self._ws: WebSocketClientProtocol | None = None
        self._session_id: str = ""
        self._subscriptions: dict[str, Callable] = {}  # symbol_key -> callback
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    async def connect(self) -> None:
        """Establish WebSocket connection to TradingView."""
        logger.info("tradingview_ws_connecting")

        self._ws = await websockets.connect(
            WS_URL,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
        )

        self._session_id = _generate_session_id("qs")
        await self._send_message("quote_create_session", [self._session_id])
        await self._send_message("quote_set_fields", [self._session_id, *QUOTE_FIELDS])

        logger.info("tradingview_ws_connected", session_id=self._session_id)
        self._reconnect_delay = 1.0

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        self._running = False

        if self._ws is not None:
            await self._ws.close()
            self._ws = None

        logger.info("tradingview_ws_disconnected")

    async def _send_message(self, method: str, params: list[Any]) -> None:
        """Send a message to TradingView.

        Args:
            method: Method name.
            params: Method parameters.
        """
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")

        message = _create_message(method, params)
        await self._ws.send(message)

        logger.debug("tradingview_ws_sent", method=method)

    async def subscribe(
        self,
        symbol: str,
        exchange: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> str:
        """Subscribe to real-time quotes for a symbol.

        Args:
            symbol: Trading symbol (e.g., "AAPL").
            exchange: Exchange name (e.g., "NASDAQ").
            callback: Async callback function for quote updates.

        Returns:
            Subscription key.
        """
        if self._ws is None:
            raise RuntimeError("WebSocket not connected. Call connect() first.")

        symbol_key = f"{exchange}:{symbol}".upper()
        self._subscriptions[symbol_key] = callback
        await self._send_message("quote_add_symbols", [self._session_id, symbol_key])
        logger.info("tradingview_ws_subscribed", symbol=symbol_key)
        return symbol_key

    async def unsubscribe(self, symbol: str, exchange: str) -> None:
        """Unsubscribe from a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
        """
        if self._ws is None:
            return

        symbol_key = f"{exchange}:{symbol}".upper()

        if symbol_key in self._subscriptions:
            del self._subscriptions[symbol_key]

            await self._send_message(
                "quote_remove_symbols",
                [self._session_id, symbol_key],
            )

            logger.info("tradingview_ws_unsubscribed", symbol=symbol_key)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle an incoming WebSocket message.

        Args:
            message: Parsed message dictionary.
        """
        method = message.get("m")
        params = message.get("p", [])

        if method == "qsd":
            # Quote data update
            await self._handle_quote_update(params)
        elif method == "quote_completed":
            logger.debug("tradingview_quote_completed", params=params)
        elif method == "critical_error":
            logger.error("tradingview_critical_error", params=params)
        elif method == "protocol_error":
            logger.error("tradingview_protocol_error", params=params)

    async def _handle_quote_update(self, params: list[Any]) -> None:
        """Handle quote data update.

        Args:
            params: Quote update parameters.
        """
        if len(params) < 2:
            return

        session_id = params[0]
        quote_data = params[1]

        if session_id != self._session_id:
            return

        symbol_key = quote_data.get("n", "")  # Symbol name like "NASDAQ:AAPL"
        values = quote_data.get("v", {})

        if not symbol_key or not values:
            return

        quote_update = {
            "symbol_key": symbol_key,
            "timestamp": datetime.utcnow(),
            "last_price": values.get("lp"),
            "volume": values.get("volume"),
            "bid": values.get("bid"),
            "ask": values.get("ask"),
            "change": values.get("ch"),
            "change_percent": values.get("chp"),
            "open_price": values.get("open_price"),
            "high_price": values.get("high_price"),
            "low_price": values.get("low_price"),
            "prev_close": values.get("prev_close_price"),
        }

        callback = self._subscriptions.get(symbol_key)
        if callback:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(quote_update)
                else:
                    callback(quote_update)
            except Exception as e:
                logger.error(
                    "tradingview_callback_error",
                    symbol=symbol_key,
                    error=str(e),
                )

    async def _send_heartbeat(self) -> None:
        """Send heartbeat to keep connection alive."""
        if self._ws is not None:
            try:
                await self._ws.send("~h~1")
            except Exception:
                pass

    async def run_forever(self) -> None:
        """Run the WebSocket client forever with auto-reconnect."""
        self._running = True

        while self._running:
            try:
                if self._ws is None:
                    await self.connect()

                    # Re-subscribe after reconnect
                    for symbol_key in list(self._subscriptions.keys()):
                        await self._send_message("quote_add_symbols", [self._session_id, symbol_key])

                async for raw_data in self._ws:
                    if not self._running:
                        break
                    if "~h~" in raw_data:
                        await self._send_heartbeat()
                        continue
                    for message in _parse_messages(raw_data):
                        await self._handle_message(message)

            except websockets.ConnectionClosed as e:
                logger.warning(
                    "tradingview_ws_connection_closed",
                    code=e.code,
                    reason=e.reason,
                )
                self._ws = None

                if self._running:
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2,
                        self._max_reconnect_delay,
                    )

            except Exception as e:
                logger.error("tradingview_ws_error", error=str(e))
                self._ws = None

                if self._running:
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2,
                        self._max_reconnect_delay,
                    )

    def is_connected(self) -> bool:
        """Check if WebSocket is connected.

        Returns:
            True if connected, False otherwise.
        """
        return self._ws is not None and self._ws.open

    @property
    def subscription_count(self) -> int:
        """Get number of active subscriptions."""
        return len(self._subscriptions)
