import asyncio
import inspect
import json
import random
import re
import string
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import websockets
from websockets import State
from websockets.asyncio.client import ClientConnection

from src.common.logging import get_logger

logger = get_logger(__name__)

WS_URL = "wss://data.tradingview.com/socket.io/websocket"

QUOTE_FIELDS = [
    "lp",
    "volume",
    "bid",
    "ask",
    "ch",
    "chp",
    "open_price",
    "high_price",
    "low_price",
    "prev_close_price",
]


def _generate_session_id(prefix: str = "qs") -> str:
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(random.choices(chars, k=12))
    return f"{prefix}_{random_part}"


def _create_message(method: str, params: list[Any]) -> str:
    message = json.dumps({"m": method, "p": params})
    return f"~m~{len(message)}~m~{message}"


def _parse_messages(raw_data: str) -> list[dict[str, Any]]:
    messages = []

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
    def __init__(self, auth_token: str | None = None):
        self._auth_token = auth_token
        self._ws: ClientConnection | None = None
        self._session_id: str = ""
        self._subscriptions: dict[str, Callable] = {}
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    async def connect(self) -> None:
        logger.info("tradingview_ws.connecting")

        self._ws = await websockets.connect(
            WS_URL,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
            additional_headers={
                "Origin": "https://www.tradingview.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )

        self._session_id = _generate_session_id("qs")
        await self._send_message("quote_create_session", [self._session_id])
        await self._send_message("quote_set_fields", [self._session_id, *QUOTE_FIELDS])

        logger.info("tradingview_ws.connected", session_id=self._session_id)
        self._reconnect_delay = 1.0

    async def disconnect(self) -> None:
        self._running = False

        if self._ws is not None:
            await self._ws.close()
            self._ws = None

        logger.info("tradingview_ws.disconnected")

    async def _send_message(self, method: str, params: list[Any]) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")

        message = _create_message(method, params)
        await self._ws.send(message)

        logger.debug("tradingview_ws.sent", method=method)

    async def subscribe(
        self,
        symbol: str,
        exchange: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> str:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected. Call connect() first.")

        symbol_key = f"{exchange}:{symbol}".upper()
        self._subscriptions[symbol_key] = callback
        await self._send_message("quote_add_symbols", [self._session_id, symbol_key])
        logger.info("tradingview_ws.subscribed", symbol=symbol_key)
        return symbol_key

    async def unsubscribe(self, symbol: str, exchange: str) -> None:
        if self._ws is None:
            return

        symbol_key = f"{exchange}:{symbol}".upper()

        if symbol_key in self._subscriptions:
            del self._subscriptions[symbol_key]

            await self._send_message(
                "quote_remove_symbols",
                [self._session_id, symbol_key],
            )

            logger.info("tradingview_ws.unsubscribed", symbol=symbol_key)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        method = message.get("m")
        params = message.get("p", [])

        if method == "qsd":
            await self._handle_quote_update(params)
        elif method == "quote_completed":
            logger.debug("tradingview_ws.quote_completed", params=params)
        elif method == "critical_error":
            logger.error("tradingview_ws.critical_error", params=params)
        elif method == "protocol_error":
            logger.error("tradingview_ws.protocol_error", params=params)

    async def _handle_quote_update(self, params: list[Any]) -> None:
        if len(params) < 2:
            return

        session_id = params[0]
        quote_data = params[1]

        if session_id != self._session_id:
            return

        symbol_key = quote_data.get("n", "")
        values = quote_data.get("v", {})

        if not symbol_key or not values:
            return

        quote_update = {
            "symbol_key": symbol_key,
            "timestamp": datetime.now(UTC),
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

        # Log only fields with values
        log_data = {k: v for k, v in quote_update.items() if v is not None}
        logger.info("tradingview_ws.quote_update", **log_data)

        callback = self._subscriptions.get(symbol_key)
        if callback:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(quote_update)
                else:
                    callback(quote_update)
            except Exception as e:
                logger.error(
                    "tradingview_ws.callback_failed",
                    symbol=symbol_key,
                    error=str(e),
                )

    async def _send_heartbeat(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send("~h~1")
            except Exception as e:
                logger.debug("tradingview_ws.heartbeat_failed", error=str(e))

    async def run_forever(self) -> None:
        self._running = True

        while self._running:
            try:
                if self._ws is None:
                    await self.connect()

                    for symbol_key in list(self._subscriptions.keys()):
                        params = [self._session_id, symbol_key]
                        await self._send_message("quote_add_symbols", params)

                async for raw_data in self._ws:
                    if not self._running:
                        break
                    # Ensure raw_data is string (API returns str | bytes)
                    data_str = raw_data if isinstance(raw_data, str) else raw_data.decode()

                    # Handle heartbeat - echo back with ~m~ wrapper format
                    if "~h~" in data_str and self._ws is not None:
                        match = re.search(r"~h~(\d+)", data_str)
                        if match:
                            heartbeat_content = f"~h~{match.group(1)}"
                            await self._ws.send(f"~m~{len(heartbeat_content)}~m~{heartbeat_content}")

                    # Parse and handle all messages (including those in same frame as heartbeat)
                    for message in _parse_messages(data_str):
                        await self._handle_message(message)

            except websockets.ConnectionClosed as e:
                logger.warning(
                    "tradingview_ws.connection_closed",
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
                logger.error("tradingview_ws.error", error=str(e))
                self._ws = None

                if self._running:
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2,
                        self._max_reconnect_delay,
                    )

    def is_connected(self) -> bool:
        if self._ws is None:
            return False
        return self._ws.state is State.OPEN

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)
