"""OKX broker implementation for live trading."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog

from src.domain.order import OrderAggregate, OrderStatus
from src.domain.position import PositionAggregate
from src.infrastructure.brokers.interface import IBroker
from src.infrastructure.brokers.models import AccountBalance, OrderResult
from src.infrastructure.brokers.okx.okx_mapper import (
    map_okx_balance_to_domain,
    map_okx_position_to_domain,
    map_order_to_okx_params,
)

logger = structlog.get_logger(__name__)


class OKXBroker(IBroker):
    """Live trading broker via OKX exchange API.

    Uses python-okx SDK for REST and WebSocket communication.
    Supports demo mode for testing without real funds.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        demo: bool = True,
        inst_suffix: str = "USDT",
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._demo = demo
        self._inst_suffix = inst_suffix

        # SDK instances (lazy initialized)
        self._trade_api: Any = None
        self._account_api: Any = None
        self._ws_client: Any = None

        self._order_callbacks: list[Callable[[OrderResult], None]] = []
        self._connected = False
        self._ws_task: asyncio.Task | None = None

    @property
    def name(self) -> str:
        return "okx-demo" if self._demo else "okx"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Initialize OKX API clients."""
        try:
            # Import OKX SDK
            from okx import Account, Trade

            # Flag: "1" for demo, "0" for live
            flag = "1" if self._demo else "0"

            self._trade_api = Trade.TradeAPI(
                self._api_key,
                self._api_secret,
                self._passphrase,
                flag=flag,
                debug=False,
            )

            self._account_api = Account.AccountAPI(
                self._api_key,
                self._api_secret,
                self._passphrase,
                flag=flag,
                debug=False,
            )

            self._connected = True
            logger.info("okx_broker_connected", demo=self._demo)

        except ImportError:
            logger.error("okx_sdk_not_installed")
            raise RuntimeError("python-okx package not installed")
        except Exception as e:
            logger.error("okx_broker_connect_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close OKX connections."""
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        self._connected = False
        logger.info("okx_broker_disconnected")

    async def submit_order(self, order: OrderAggregate) -> OrderResult:
        """Submit order to OKX via REST API."""
        if not self._connected or not self._trade_api:
            return OrderResult(
                order_id=order.id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                error_message="Broker not connected",
            )

        try:
            params = map_order_to_okx_params(order, self._inst_suffix)

            # Run blocking SDK call in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._trade_api.place_order(**params)
            )

            # Parse response
            if response.get("code") != "0":
                error_msg = response.get("msg", "Unknown error")
                logger.warning(
                    "okx_order_rejected",
                    order_id=order.id,
                    error=error_msg,
                )
                return OrderResult(
                    order_id=order.id,
                    broker_order_id="",
                    status=OrderStatus.REJECTED,
                    error_message=error_msg,
                )

            # Extract order data
            data = response.get("data", [{}])[0]
            broker_order_id = data.get("ordId", "")
            state = data.get("sCode", "0")

            # sCode "0" means success, order is live
            status = OrderStatus.SUBMITTED if state == "0" else OrderStatus.REJECTED

            logger.info(
                "okx_order_submitted",
                order_id=order.id,
                broker_order_id=broker_order_id,
                status=status.value,
            )

            result = OrderResult(
                order_id=order.id,
                broker_order_id=broker_order_id,
                status=status,
                submitted_at=datetime.now(UTC),
            )

            # Notify callbacks
            await self._notify_callbacks(result)

            return result

        except Exception as e:
            logger.error("okx_order_submit_failed", order_id=order.id, error=str(e))
            return OrderResult(
                order_id=order.id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                error_message=str(e),
            )

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel order on OKX."""
        if not self._connected or not self._trade_api:
            return False

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._trade_api.cancel_order(
                    instId="", ordId=broker_order_id  # OKX requires instId but can be empty
                ),
            )

            success = response.get("code") == "0"
            logger.info(
                "okx_order_cancelled",
                broker_order_id=broker_order_id,
                success=success,
            )
            return success

        except Exception as e:
            logger.error(
                "okx_order_cancel_failed",
                broker_order_id=broker_order_id,
                error=str(e),
            )
            return False

    async def get_positions(self) -> list[PositionAggregate]:
        """Get open positions from OKX."""
        if not self._connected or not self._account_api:
            return []

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._account_api.get_positions()
            )

            if response.get("code") != "0":
                logger.warning("okx_get_positions_failed", error=response.get("msg"))
                return []

            positions = []
            for pos_data in response.get("data", []):
                pos = map_okx_position_to_domain(pos_data, strategy_id="okx")
                if pos:
                    positions.append(pos)

            return positions

        except Exception as e:
            logger.error("okx_get_positions_error", error=str(e))
            return []

    async def get_balance(self) -> AccountBalance:
        """Get account balance from OKX."""
        if not self._connected or not self._account_api:
            return AccountBalance(
                total_equity=0, available_balance=0, currency="USDT"
            )

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._account_api.get_account_balance()
            )

            if response.get("code") != "0":
                logger.warning("okx_get_balance_failed", error=response.get("msg"))
                return AccountBalance(
                    total_equity=0, available_balance=0, currency="USDT"
                )

            data = response.get("data", [{}])[0]
            balance_dict = map_okx_balance_to_domain(data)

            return AccountBalance(**balance_dict)

        except Exception as e:
            logger.error("okx_get_balance_error", error=str(e))
            return AccountBalance(
                total_equity=0, available_balance=0, currency="USDT"
            )

    async def subscribe_order_updates(
        self, callback: Callable[[OrderResult], None]
    ) -> None:
        """Subscribe to order updates via WebSocket."""
        self._order_callbacks.append(callback)

        # Start WebSocket listener if not running
        if not self._ws_task:
            self._ws_task = asyncio.create_task(self._ws_listener())

    async def unsubscribe_order_updates(self) -> None:
        """Unsubscribe from order updates."""
        self._order_callbacks.clear()

        if self._ws_task:
            self._ws_task.cancel()
            self._ws_task = None

    async def _ws_listener(self) -> None:
        """WebSocket listener for order updates.

        Note: Full WebSocket implementation would use okx.websocket module.
        This is a placeholder for the pattern - actual implementation
        requires careful handling of reconnection and message parsing.
        """
        logger.info("okx_ws_listener_started")

        try:
            while self._connected:
                # Placeholder: In full implementation, connect to OKX WS
                # and listen for order channel updates
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("okx_ws_listener_cancelled")
        except Exception as e:
            logger.error("okx_ws_listener_error", error=str(e))

    async def _notify_callbacks(self, result: OrderResult) -> None:
        """Notify all registered callbacks of order update."""
        for callback in self._order_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except Exception as e:
                logger.warning("okx_callback_error", error=str(e))
