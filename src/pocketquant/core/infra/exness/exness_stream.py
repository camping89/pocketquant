"""One reconnecting, signed Exness WebSocket stream on the account's access point.

Shaped like ``BinanceWebSocketAdapter``: exponential backoff from 1 s to 30 s,
and a circuit breaker that pauses for 300 s after 10 consecutive failures. A
handler exception never kills the stream, and ``run_forever`` raises nothing
but ``CancelledError``, because the realtime router gathers every child feed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import websockets
from websockets.typing import Subprotocol

from pocketquant.core.common.logging import get_logger
from pocketquant.core.infra.exness.exness_client import ExnessClient

logger = get_logger(__name__)

# The spike recorded that the server selects this subprotocol.
_SUBPROTOCOL = Subprotocol("exness-ws-protocol")
_BACKOFF_INITIAL_S = 1.0
_BACKOFF_MAX_S = 30.0
_BREAKER_FAILURES = 10
_BREAKER_PAUSE_S = 300.0
_WATCHDOG_INTERVAL_S = 5.0


class ExnessStream:
    """A signed WS stream that reconnects until closed."""

    def __init__(
        self,
        client: ExnessClient,
        path: str,
        on_message: Callable[[dict[str, Any]], Awaitable[None]],
        on_connect: Callable[[], Awaitable[None]],
        stale_after_s: float | None,
    ) -> None:
        self._client = client
        self._path = path
        self._on_message = on_message
        self._on_connect = on_connect
        self._stale_after_s = stale_after_s
        self._ws: Any = None
        self._running = False
        self._delay = _BACKOFF_INITIAL_S
        self._failures = 0
        self.last_frame_at: datetime | None = None

    async def run_forever(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._run_connection()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("exness_ws.connection_failed", error=type(exc).__name__)
            finally:
                await self._close_ws()
            if self._running:
                await self._backoff()

    async def _run_connection(self) -> None:
        url = await self._client.ws_url(self._path)
        self._ws = await websockets.connect(
            url,
            additional_headers=self._client.sign_ws_headers(self._path),
            subprotocols=[_SUBPROTOCOL],
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        )
        self._delay = _BACKOFF_INITIAL_S
        self._failures = 0
        self.last_frame_at = datetime.now(UTC)
        logger.info("exness_ws.connected")
        await self._on_connect()
        watchdog = asyncio.create_task(self._watchdog()) if self._stale_after_s else None
        try:
            async for raw in self._ws:
                await self._handle(raw)
        finally:
            if watchdog is not None:
                watchdog.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await watchdog
        logger.info("exness_ws.disconnected")

    async def _handle(self, raw: str | bytes) -> None:
        try:
            frame = json.loads(raw)
        except ValueError:
            logger.warning("exness_ws.invalid_json")
            return
        if not isinstance(frame, dict):
            logger.warning("exness_ws.invalid_json")
            return
        self.last_frame_at = datetime.now(UTC)
        try:
            await self._on_message(frame)
        except Exception as exc:
            logger.warning("exness_ws.handler_failed", error=type(exc).__name__)

    async def _backoff(self) -> None:
        self._failures += 1
        if self._failures >= _BREAKER_FAILURES:
            logger.error("exness_ws.circuit_breaker_open", failures=self._failures)
            self._failures = 0
            await asyncio.sleep(_BREAKER_PAUSE_S)
            return
        logger.info("exness_ws.reconnecting", delay=self._delay)
        await asyncio.sleep(self._delay)
        self._delay = min(self._delay * 2, _BACKOFF_MAX_S)

    async def _watchdog(self) -> None:
        """Close the socket when no frame arrived for ``stale_after_s``."""
        assert self._stale_after_s is not None
        while True:
            await asyncio.sleep(_WATCHDOG_INTERVAL_S)
            last = self.last_frame_at
            if last is None:
                continue
            lag = (datetime.now(UTC) - last).total_seconds()
            if lag > self._stale_after_s:
                logger.warning("exness_ws.stale_detected", lag_seconds=lag)
                await self._close_ws()
                return

    async def send(self, message: dict[str, Any]) -> None:
        if not self.is_connected():
            logger.debug("exness_ws.send_skipped_not_connected")
            return
        await self._ws.send(json.dumps(message))

    def is_connected(self) -> bool:
        if self._ws is None:
            return False
        return getattr(self._ws, "state", None) is websockets.State.OPEN

    async def close(self) -> None:
        self._running = False
        await self._close_ws()

    async def _close_ws(self) -> None:
        if self._ws is None:
            return
        ws, self._ws = self._ws, None
        with contextlib.suppress(Exception):
            await ws.close()
