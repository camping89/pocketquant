"""OKX reconnection handler - exponential backoff and state sync on reconnect."""

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from pocketquant.core.infra.brokers.okx.websocket.okx_websocket_client import OkxWebSocketClient

if TYPE_CHECKING:
    from pocketquant.core.infra.brokers.okx.okx_broker import OKXBroker

logger = structlog.get_logger(__name__)

# Reconnection configuration
DEFAULT_INITIAL_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0  # seconds
DEFAULT_MULTIPLIER = 2.0
CIRCUIT_BREAKER_FAILURES = 10  # After 10 consecutive failures
CIRCUIT_BREAKER_PAUSE = 300.0  # 5 minute pause (validated requirement)


class OkxReconnectionHandler:
    """Handles WebSocket reconnection with exponential backoff.

    Features:
    - Exponential backoff: 1s, 2s, 4s, 8s, ... up to 30s max
    - Circuit breaker: Pause 5 minutes after 10 consecutive failures
    - State sync: Fetch open orders and positions via REST after reconnect
    - Deduplication update: Refresh terminal order set to prevent re-processing

    Usage:
        handler = OkxReconnectionHandler(ws_client, broker)
        await handler.handle_disconnect()  # Called when WS disconnects
    """

    def __init__(
        self,
        ws_client: OkxWebSocketClient,
        broker: OKXBroker,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        multiplier: float = DEFAULT_MULTIPLIER,
    ) -> None:
        self._ws_client = ws_client
        self._broker = broker
        self._initial_delay = initial_delay
        self._max_delay = max_delay
        self._multiplier = multiplier

        self._reconnecting = False
        self._consecutive_failures = 0

    async def handle_disconnect(self) -> None:
        """Handle WebSocket disconnection - start reconnection process.

        Implements exponential backoff with circuit breaker.
        """
        if self._reconnecting:
            logger.debug("okx_reconnect_already_in_progress")
            return

        self._reconnecting = True
        delay = self._initial_delay

        logger.info("okx_reconnect_starting")

        while self._reconnecting:
            if self._consecutive_failures >= CIRCUIT_BREAKER_FAILURES:
                logger.warning(
                    "okx_circuit_breaker_triggered",
                    failures=self._consecutive_failures,
                    pause_seconds=CIRCUIT_BREAKER_PAUSE,
                )
                await asyncio.sleep(CIRCUIT_BREAKER_PAUSE)
                self._consecutive_failures = 0  # Reset after pause
                delay = self._initial_delay

            logger.info("okx_reconnect_attempt", delay=delay, failures=self._consecutive_failures)
            await asyncio.sleep(delay)

            try:
                await self._ws_client.connect()

                await self._sync_state()

                await self._ws_client.subscribe(
                    [
                        {"channel": "orders", "instType": "SWAP"},
                        {"channel": "positions", "instType": "SWAP"},
                    ]
                )

                self._reconnecting = False
                self._consecutive_failures = 0

                logger.info("okx_reconnect_success")
                return

            except Exception as e:
                self._consecutive_failures += 1
                logger.warning(
                    "okx_reconnect_failed",
                    error=str(e),
                    failures=self._consecutive_failures,
                )

                delay = min(delay * self._multiplier, self._max_delay)

    async def _sync_state(self) -> None:
        """Sync state from REST API after reconnect.

        Fetches open orders and recent order history to:
        1. Update deduplication set with terminal orders
        2. Detect any orders that filled while disconnected
        """
        logger.info("okx_state_sync_starting")

        try:
            # Sync terminal orders to deduplication set
            await self._update_terminal_orders()

            # Fetch current positions (for logging/monitoring)
            positions = await self._broker.get_positions()
            logger.info("okx_state_synced", positions=len(positions))

        except Exception as e:
            logger.error("okx_state_sync_failed", error=str(e))
            # Don't raise - reconnection succeeded, sync failure is non-fatal

    async def _update_terminal_orders(self) -> None:
        """Fetch recent order history and update deduplication set.

        This prevents re-processing of orders that reached terminal state
        while we were disconnected.
        """
        if not self._broker.trade_api:
            return

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._broker.trade_api.get_orders_history(instType="SWAP", limit="100"),
            )

            if response.get("code") != "0":
                logger.warning(
                    "okx_fetch_order_history_failed",
                    error=response.get("msg"),
                )
                return

            terminal_count = 0
            for order in response.get("data", []):
                state = order.get("state", "")
                if state in ("filled", "canceled", "mmp_canceled"):
                    ord_id = order.get("ordId", "")
                    if ord_id:
                        self._broker.seen_terminal_orders.add(ord_id)
                        terminal_count += 1

            logger.info("okx_terminal_orders_synced", count=terminal_count)

        except Exception as e:
            logger.warning("okx_update_terminal_orders_error", error=str(e))

    def stop(self) -> None:
        self._reconnecting = False
        logger.info("okx_reconnect_stopped")


class OkxStateReconciler:
    """Reconciles local state with OKX REST after reconnect to detect missed fills."""

    def __init__(self, broker: OKXBroker) -> None:
        self._broker = broker

    async def sync(self) -> dict[str, Any]:
        """Fetch REST state and return summary.

        Returns:
            Dict with sync results (orders count, positions count).
        """
        open_orders = await self._fetch_open_orders()
        positions = await self._broker.get_positions()

        return {
            "open_orders": len(open_orders),
            "positions": len(positions),
        }

    async def _fetch_open_orders(self) -> list[dict]:
        if not self._broker.trade_api:
            return []

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._broker.trade_api.get_order_list(instType="SWAP"),
            )

            if response.get("code") != "0":
                logger.warning(
                    "okx_fetch_open_orders_failed",
                    error=response.get("msg"),
                )
                return []

            return response.get("data", [])

        except Exception as e:
            logger.error("okx_fetch_open_orders_error", error=str(e))
            return []
