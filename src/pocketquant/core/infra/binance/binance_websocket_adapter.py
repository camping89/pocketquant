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
from pocketquant.core.infra.binance.binance_mappers import (
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
_SUBSCRIPTION_POLL_S = 0.1


class BinanceWebSocketAdapter:
    def __init__(self) -> None:
        # composite_symbol -> (code, callback) — composite is e.g. "BTCUSDT:BINANCE"
        self._subscriptions: dict[str, tuple[str, Callable[[dict[str, Any]], Any]]] = {}
        self._ws: Any = None  # websockets.ClientConnection | None
        self._running = False
        self._reconnect_delay = _RECONNECT_DELAY_INITIAL
        self.last_tick_at: datetime | None = None

    async def connect(self) -> None:
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
        # Extract bare code for Binance API stream name (BINANCE-specific boundary)
        code = symbol.split(":")[0] if ":" in symbol else symbol
        validated = validate_symbol(code)
        composite = symbol.upper()
        self._subscriptions[composite] = (validated, callback)
        logger.info("binance_ws.subscribed", symbol=composite)
        return composite

    async def unsubscribe(self, symbol: str) -> None:
        # Local only: the stream URL is built at connect, so the open stream
        # keeps the symbol until the next reconnect.
        composite = symbol.upper()
        if composite in self._subscriptions:
            del self._subscriptions[composite]
            logger.info("binance_ws.unsubscribed", symbol=composite)

    async def run_forever(self) -> None:
        self._running = True

        while self._running:
            watchdog: asyncio.Task[None] | None = None
            try:
                if self._ws is None:
                    # The URL names the subscribed streams; Binance rejects one with
                    # none (HTTP 400), so the first connect waits for a subscription.
                    while self._running and not self._subscriptions:
                        await asyncio.sleep(_SUBSCRIPTION_POLL_S)
                    if not self._running:
                        break
                    await self.connect()
                    # Reset baseline so the watchdog doesn't trip immediately
                    self.last_tick_at = datetime.now(UTC)

                watchdog = asyncio.create_task(self._stale_connection_watchdog())

                async for raw_frame in self._ws:
                    if not self._running:
                        break
                    await self._handle_frame(raw_frame)

                # websockets does not raise on a normal close (1000/1001); reconnect anyway.
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
        return self._subscriptions

    def _build_url(self) -> str:
        streams = [f"{code.lower()}@aggTrade" for code, _cb in self._subscriptions.values()]
        if len(streams) == 1:
            return f"{_WS_BASE}/ws/{streams[0]}"
        return f"{_WS_BASE}/stream?streams={'/'.join(streams)}"

    async def _handle_frame(self, raw_frame: str | bytes) -> None:
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
        logger.info("binance_ws.reconnecting", delay=self._reconnect_delay)
        await asyncio.sleep(self._reconnect_delay)
        self._reconnect_delay = min(self._reconnect_delay * 2, _RECONNECT_DELAY_MAX)

    async def _close_ws(self) -> None:
        if self._ws is None:
            return
        with contextlib.suppress(Exception):
            await self._ws.close()
        self._ws = None

    # A dead socket can stay open and neither yield nor raise (seen with websockets 16.0 +
    # Python 3.14). Closing it from this sibling task unblocks the iterator in run_forever.
    async def _stale_connection_watchdog(self) -> None:
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
