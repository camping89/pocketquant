"""Binance WebSocket client — @aggTrade per-trade stream.

Supports single and combined-stream subscriptions.
Single:   wss://stream.binance.com:9443/ws/{symbol}@aggTrade
Combined: wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade

volume in callback dict = raw per-trade quantity (delta, NOT cumulative).
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import websockets
from pocketquant.core.common.logging import get_logger
from pocketquant.core.infrastructure.binance.binance_mappers import (
    aggtrade_to_quote_dict,
    validate_symbol,
)

logger = get_logger(__name__)

_WS_BASE = "wss://stream.binance.com:9443"
_RECONNECT_DELAY_INITIAL = 1.0
_RECONNECT_DELAY_MAX = 60.0


class BinanceWebSocketClient:
    """Realtime @aggTrade stream client for Binance public WebSocket API.

    Usage:
        client = BinanceWebSocketClient()
        await client.subscribe("BTCUSDT", "BINANCE", my_callback)
        await client.run_forever()   # blocks; reconnects on drop
    """

    def __init__(self) -> None:
        # symbol_key -> (symbol, exchange, callback)
        self._subscriptions: dict[str, tuple[str, str, Callable[[dict[str, Any]], Any]]] = {}
        self._ws: Any = None  # websockets.ClientConnection | None
        self._running = False
        self._reconnect_delay = _RECONNECT_DELAY_INITIAL
        self.last_tick_at: datetime | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open WebSocket to Binance stream URL based on current subscriptions."""
        url = self._build_url()
        self._ws = await websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        )
        self._reconnect_delay = _RECONNECT_DELAY_INITIAL
        logger.info("binance_ws.connected", url=url, streams=list(self._subscriptions.keys()))

    async def disconnect(self) -> None:
        """Stop run_forever loop and close connection."""
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        logger.info("binance_ws.disconnected")

    async def subscribe(
        self,
        symbol: str,
        exchange: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> str:
        """Register a symbol subscription. Returns the symbol_key."""
        validated = validate_symbol(symbol)
        symbol_key = f"{exchange.upper()}:{validated}"
        self._subscriptions[symbol_key] = (validated, exchange.upper(), callback)
        logger.info("binance_ws.subscribed", symbol_key=symbol_key)
        return symbol_key

    async def unsubscribe(self, symbol: str, exchange: str) -> None:
        """Remove a subscription. Does not reconnect automatically."""
        validated = validate_symbol(symbol)
        symbol_key = f"{exchange.upper()}:{validated}"
        if symbol_key in self._subscriptions:
            del self._subscriptions[symbol_key]
            logger.info("binance_ws.unsubscribed", symbol_key=symbol_key)

    async def run_forever(self) -> None:
        """Connect and receive messages, reconnecting with exponential backoff on failure."""
        self._running = True

        while self._running:
            try:
                if self._ws is None:
                    await self.connect()

                async for raw_frame in self._ws:
                    if not self._running:
                        break
                    await self._handle_frame(raw_frame)

            except websockets.ConnectionClosed as exc:
                logger.warning("binance_ws.connection_closed", code=exc.code, reason=exc.reason)
                self._ws = None
                if self._running:
                    await self._backoff_sleep()

            except Exception as exc:
                logger.error("binance_ws.error", error=str(exc))
                self._ws = None
                if self._running:
                    await self._backoff_sleep()

    def is_connected(self) -> bool:
        """Return True when the underlying WebSocket is open."""
        if self._ws is None:
            return False
        try:
            from websockets import State

            return self._ws.state is State.OPEN  # type: ignore[attr-defined]
        except Exception:
            return False

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)

    @property
    def subscriptions(self) -> dict[str, tuple[str, str, Callable[[dict[str, Any]], Any]]]:
        """Return subscriptions dict: symbol_key -> (symbol, exchange, callback)."""
        return self._subscriptions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_url(self) -> str:
        """Build stream URL: single or combined depending on subscription count."""
        streams = [f"{sym.lower()}@aggTrade" for sym, _exch, _cb in self._subscriptions.values()]
        if len(streams) == 1:
            return f"{_WS_BASE}/ws/{streams[0]}"
        if len(streams) > 1:
            return f"{_WS_BASE}/stream?streams={'/'.join(streams)}"
        # No subscriptions yet — use a placeholder; connect() called before subscribe
        return f"{_WS_BASE}/ws/"

    async def _handle_frame(self, raw_frame: str | bytes) -> None:
        """Parse a raw WebSocket frame and dispatch to callbacks."""
        text = raw_frame if isinstance(raw_frame, str) else raw_frame.decode()
        try:
            frame = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("binance_ws.invalid_json", error=str(exc))
            return

        # Combined-stream wraps the event under "data" key
        event: dict[str, Any] = frame.get("data", frame)

        if event.get("e") != "aggTrade":
            return

        raw_symbol: str = event.get("s", "")
        # Find the matching subscription by symbol (case-insensitive)
        for symbol_key, (sym, exch, callback) in self._subscriptions.items():
            if sym.upper() == raw_symbol.upper():
                quote_dict = aggtrade_to_quote_dict(event, sym, exch)
                self.last_tick_at = datetime.now(UTC)
                logger.info(
                    "binance_ws.aggtrade_received",
                    symbol_key=symbol_key,
                    last_price=quote_dict["last_price"],
                    volume=quote_dict["volume"],
                )
                await self._invoke_callback(callback, quote_dict, symbol_key)
                break

    async def _invoke_callback(
        self,
        callback: Callable[[dict[str, Any]], Any],
        data: dict[str, Any],
        symbol_key: str,
    ) -> None:
        try:
            if inspect.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)
        except Exception as exc:
            logger.error("binance_ws.callback_failed", symbol=symbol_key, error=str(exc))
            raise

    async def _backoff_sleep(self) -> None:
        """Sleep for current backoff delay then double it (capped at max)."""
        logger.info("binance_ws.reconnecting", delay=self._reconnect_delay)
        await asyncio.sleep(self._reconnect_delay)
        self._reconnect_delay = min(self._reconnect_delay * 2, _RECONNECT_DELAY_MAX)
