"""Binance WebSocket client — @aggTrade per-trade stream.

Supports single and combined-stream subscriptions.
Single:   wss://stream.binance.com:9443/ws/{symbol}@aggTrade
Combined: wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade

volume in callback dict = raw per-trade quantity (delta, NOT cumulative).
"""

from __future__ import annotations

import asyncio
import contextlib
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
# Watchdog: force-reconnect if no frame received for this long.
# Defends against websockets/asyncio bugs where `async for` neither yields
# nor raises after the underlying socket has died.
_STALE_TICK_TIMEOUT_S = 30.0
_WATCHDOG_INTERVAL_S = 5.0


class BinanceWebSocketClient:
    """Realtime @aggTrade stream client for Binance public WebSocket API.

    Usage:
        client = BinanceWebSocketClient()
        await client.subscribe("BTCUSDT:BINANCE", my_callback)
        await client.run_forever()   # blocks; reconnects on drop
    """

    def __init__(self) -> None:
        # composite_symbol -> (code, callback) — composite is e.g. "BTCUSDT:BINANCE"
        self._subscriptions: dict[str, tuple[str, Callable[[dict[str, Any]], Any]]] = {}
        self._ws: Any = None  # websockets.ClientConnection | None
        self._running = False
        self._reconnect_delay = _RECONNECT_DELAY_INITIAL
        self.last_tick_at: datetime | None = None

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
        callback: Callable[[dict[str, Any]], Any],
    ) -> str:
        """Register a symbol subscription. ``symbol`` is composite ``{code}:{exchange}``. Returns key."""
        # Extract bare code for Binance API stream name (BINANCE-specific boundary)
        code = symbol.split(":")[0] if ":" in symbol else symbol
        validated = validate_symbol(code)
        composite = symbol.upper()
        self._subscriptions[composite] = (validated, callback)
        logger.info("binance_ws.subscribed", symbol=composite)
        return composite

    async def unsubscribe(self, symbol: str) -> None:
        """Remove a subscription. ``symbol`` is composite ``{code}:{exchange}``."""
        composite = symbol.upper()
        if composite in self._subscriptions:
            del self._subscriptions[composite]
            logger.info("binance_ws.unsubscribed", symbol=composite)

    async def run_forever(self) -> None:
        """Connect and receive messages, reconnecting with exponential backoff on failure.

        Handles three exit modes:
        - `ConnectionClosed` raised by the iterator (abnormal close codes).
        - Silent iterator exit on normal close (1000/1001) — websockets does NOT
          raise in this case, so the silent-exit branch forces a reconnect.
        - Stale socket where the iterator neither yields nor raises (observed with
          websockets 16.0 + Python 3.14): a watchdog closes `_ws` after
          `_STALE_TICK_TIMEOUT_S` of no ticks, unblocking the iterator.
        """
        self._running = True

        while self._running:
            watchdog: asyncio.Task[None] | None = None
            try:
                if self._ws is None:
                    await self.connect()
                    # Reset baseline so the watchdog doesn't trip immediately
                    self.last_tick_at = datetime.now(UTC)

                watchdog = asyncio.create_task(self._stale_connection_watchdog())

                async for raw_frame in self._ws:
                    if not self._running:
                        break
                    await self._handle_frame(raw_frame)

                # `async for` exited silently (close 1000/1001) — treat as disconnect
                logger.warning("binance_ws.iterator_exited_silently")
                await self._close_ws()
                if self._running:
                    await self._backoff_sleep()

            except websockets.ConnectionClosed as exc:
                logger.warning("binance_ws.connection_closed", code=exc.code, reason=exc.reason)
                await self._close_ws()
                if self._running:
                    await self._backoff_sleep()

            except Exception as exc:
                logger.error("binance_ws.error", error=str(exc))
                await self._close_ws()
                if self._running:
                    await self._backoff_sleep()

            finally:
                if watchdog is not None:
                    watchdog.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await watchdog

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
    def subscriptions(self) -> dict[str, tuple[str, Callable[[dict[str, Any]], Any]]]:
        """Return subscriptions dict: composite_symbol -> (code, callback)."""
        return self._subscriptions

    def _build_url(self) -> str:
        """Build stream URL: single or combined depending on subscription count."""
        streams = [f"{code.lower()}@aggTrade" for code, _cb in self._subscriptions.values()]
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
        # Find the matching subscription by bare code (case-insensitive)
        for composite, (code, callback) in self._subscriptions.items():
            if code.upper() == raw_symbol.upper():
                quote_dict = aggtrade_to_quote_dict(event, composite)
                self.last_tick_at = datetime.now(UTC)
                # DEBUG level: aggTrade fires 50–500 times/sec/symbol; INFO logging
                # saturates event loop and blocks HTTP handlers.
                logger.debug(
                    "binance_ws.aggtrade_received",
                    symbol=composite,
                    last_price=quote_dict["last_price"],
                    volume=quote_dict["volume"],
                )
                await self._invoke_callback(callback, quote_dict, composite)
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

    async def _close_ws(self) -> None:
        """Best-effort close + clear `_ws`. Idempotent."""
        if self._ws is None:
            return
        with contextlib.suppress(Exception):
            await self._ws.close()
        self._ws = None

    async def _stale_connection_watchdog(self) -> None:
        """Force-close `_ws` if no frame has arrived for `_STALE_TICK_TIMEOUT_S`.

        Runs as a sibling task to the `async for` consumer. Closing the socket
        from outside causes the iterator to raise/return so `run_forever` can
        recover. Without this, a dead-but-not-closed socket spins the event
        loop indefinitely (observed with websockets 16.0 + Python 3.14).
        """
        while True:
            await asyncio.sleep(_WATCHDOG_INTERVAL_S)
            last = self.last_tick_at
            if last is None:
                continue
            lag = (datetime.now(UTC) - last).total_seconds()
            if lag > _STALE_TICK_TIMEOUT_S:
                logger.warning("binance_ws.stale_detected", lag_seconds=lag)
                await self._close_ws()
                return
