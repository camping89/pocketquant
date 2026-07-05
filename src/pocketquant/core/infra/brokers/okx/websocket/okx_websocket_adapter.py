"""OKX WebSocket client - private channel connection with authentication."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
import websockets
from websockets.asyncio.client import ClientConnection

from pocketquant.core.infra.brokers.okx.websocket.okx_auth import (
    build_login_message,
    get_private_ws_url,
)

logger = structlog.get_logger(__name__)

# WebSocket timeouts
CONNECT_TIMEOUT = 10.0
LOGIN_TIMEOUT = 5.0
SUBSCRIBE_TIMEOUT = 5.0
PING_INTERVAL = 25  # Send ping before 30s OKX timeout
PONG_TIMEOUT = 5.0


class OKXWebSocketAdapter:
    """WebSocket client for OKX private channels.

    Features:
    - HMAC-SHA256 authentication
    - Subscribe to orders and positions channels
    - Heartbeat (ping/pong) to maintain connection
    - Async message iteration
    - Disconnect callback for reconnection handling

    Usage:
        client = OKXWebSocketAdapter(api_key, api_secret, passphrase)
        await client.connect()
        await client.subscribe([
            {"channel": "orders", "instType": "SWAP"},
            {"channel": "positions", "instType": "SWAP"}
        ])
        async for message in client:
            handle_message(message)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        demo: bool = True,
        on_disconnect: Callable[[], Any] | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._demo = demo
        self._on_disconnect = on_disconnect

        self._ws: ClientConnection | None = None
        self._connected = False
        self._authenticated = False
        self._heartbeat_task: asyncio.Task | None = None
        self._subscribed_channels: list[dict] = []

    @property
    def ws_url(self) -> str:
        return get_private_ws_url(self._demo)

    @property
    def is_connected(self) -> bool:
        return self._connected and self._authenticated

    async def connect(self) -> None:
        """Connect to OKX WebSocket and authenticate.

        Raises:
            ConnectionError: If connection or authentication fails.
        """
        try:
            logger.info("okx_ws_connecting", url=self.ws_url, demo=self._demo)

            self._ws = await asyncio.wait_for(
                websockets.connect(self.ws_url, ping_interval=None),
                timeout=CONNECT_TIMEOUT,
            )
            self._connected = True

            await self._authenticate()

            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            logger.info("okx_ws_connected", authenticated=self._authenticated)

        except TimeoutError as e:
            logger.error("okx_ws_connect_timeout")
            raise ConnectionError("WebSocket connection timeout") from e
        except Exception as e:
            logger.error("okx_ws_connect_failed", error=str(e))
            raise ConnectionError(f"WebSocket connection failed: {e}") from e

    async def _authenticate(self) -> None:
        if not self._ws:
            raise ConnectionError("WebSocket not connected")

        login_msg = build_login_message(self._api_key, self._api_secret, self._passphrase)

        await self._ws.send(json.dumps(login_msg))

        try:
            response = await asyncio.wait_for(self._ws.recv(), timeout=LOGIN_TIMEOUT)
            data = json.loads(response)

            if data.get("event") == "login":
                if data.get("code") == "0":
                    self._authenticated = True
                    logger.info("okx_ws_authenticated")
                else:
                    error_msg = data.get("msg", "Unknown authentication error")
                    logger.error("okx_ws_auth_failed", code=data.get("code"), msg=error_msg)
                    raise ConnectionError(f"Authentication failed: {error_msg}")
            else:
                logger.warning("okx_ws_unexpected_login_response", data=data)

        except TimeoutError as e:
            logger.error("okx_ws_auth_timeout")
            raise ConnectionError("Authentication timeout") from e

    async def subscribe(self, channels: list[dict]) -> None:
        """Subscribe to OKX channels.

        Args:
            channels: List of channel specs, e.g.:
                [{"channel": "orders", "instType": "SWAP"}]

        Raises:
            ConnectionError: If not connected or subscribe fails.
        """
        if not self.is_connected:
            raise ConnectionError("WebSocket not connected or authenticated")

        subscribe_msg = {"op": "subscribe", "args": channels}

        if self._ws is None:
            raise ConnectionError("WebSocket not connected")

        await self._ws.send(json.dumps(subscribe_msg))

        try:
            response = await asyncio.wait_for(self._ws.recv(), timeout=SUBSCRIBE_TIMEOUT)
            data = json.loads(response)

            if data.get("event") == "subscribe":
                self._subscribed_channels.extend(channels)
                logger.info("okx_ws_subscribed", channels=channels)
            elif data.get("event") == "error":
                error_msg = data.get("msg", "Subscribe error")
                logger.error("okx_ws_subscribe_failed", error=error_msg)
                raise ConnectionError(f"Subscribe failed: {error_msg}")

        except TimeoutError as e:
            logger.error("okx_ws_subscribe_timeout")
            raise ConnectionError("Subscribe timeout") from e

    async def disconnect(self) -> None:
        self._connected = False
        self._authenticated = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._subscribed_channels.clear()
        logger.info("okx_ws_disconnected")

    async def _heartbeat_loop(self) -> None:
        while self._connected and self._ws:
            try:
                await asyncio.sleep(PING_INTERVAL)

                if not self._connected or not self._ws:
                    break

                await self._ws.send("ping")

                try:
                    response = await asyncio.wait_for(self._ws.recv(), timeout=PONG_TIMEOUT)
                    if response != "pong":
                        # Not a pong, put it back for message processing
                        # Note: This is simplified - real impl would use a queue
                        logger.debug("okx_ws_heartbeat_non_pong", response=response[:100])

                except TimeoutError:
                    logger.warning("okx_ws_pong_timeout")
                    await self._handle_disconnect()
                    return

            except websockets.ConnectionClosed:
                logger.warning("okx_ws_heartbeat_connection_closed")
                await self._handle_disconnect()
                return
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("okx_ws_heartbeat_error", error=str(e))

    async def _handle_disconnect(self) -> None:
        self._connected = False
        self._authenticated = False

        if self._on_disconnect:
            logger.info("okx_ws_triggering_disconnect_callback")
            if asyncio.iscoroutinefunction(self._on_disconnect):
                asyncio.create_task(self._on_disconnect())
            else:
                self._on_disconnect()

    async def __aiter__(self) -> AsyncIterator[dict]:
        """Async iterator for receiving messages.

        Yields:
            Parsed JSON messages from WebSocket.

        Note:
            Filters out pong responses and event messages (login, subscribe).
            Only yields data messages.
        """
        if not self._ws:
            raise ConnectionError("WebSocket not connected")

        try:
            async for message in self._ws:
                if message == "pong":
                    continue

                try:
                    data = json.loads(message)

                    if "event" in data:
                        if data.get("event") == "error":
                            logger.warning("okx_ws_error_event", data=data)
                        continue

                    if "data" in data:
                        yield data

                except json.JSONDecodeError as e:
                    logger.warning("okx_ws_json_decode_error", error=str(e), message=message[:100])

        except websockets.ConnectionClosed as e:
            logger.warning("okx_ws_connection_closed", code=e.code, reason=e.reason)
            await self._handle_disconnect()
        except asyncio.CancelledError:
            logger.info("okx_ws_iterator_cancelled")
        except Exception as e:
            logger.error("okx_ws_iterator_error", error=str(e))
            await self._handle_disconnect()
