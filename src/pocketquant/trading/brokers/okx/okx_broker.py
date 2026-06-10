"""OKX broker implementation for live trading."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

from pocketquant.core.domain.brokers.interfaces import IBroker, OrderCallback
from pocketquant.core.domain.brokers.value_objects import AccountBalance, OrderResult
from pocketquant.core.domain.order import OrderAggregate, OrderStatus
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.trading.brokers.okx.okx_mapper import (
    map_okx_balance_to_domain,
    map_okx_position_to_domain,
    map_order_to_okx_params,
)
from pocketquant.trading.brokers.okx.websocket import (
    OkxMessageParser,
    OkxOrderMapper,
    OkxPositionMapper,
    OkxReconnectionHandler,
    OkxWebSocketClient,
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

        self._trade_api: Any = None
        self._account_api: Any = None
        self._ws_client: OkxWebSocketClient | None = None

        self._order_callbacks: list[OrderCallback] = []
        self._connected = False
        self._ws_task: asyncio.Task | None = None

        # Deduplication set for terminal order states (filled, canceled)
        self._seen_terminal_orders: set[str] = set()

        # Reconnection handler (created when WS listener starts)
        self._reconnection_handler: OkxReconnectionHandler | None = None

    @property
    def name(self) -> str:
        return "okx-demo" if self._demo else "okx"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def trade_api(self) -> Any:
        return self._trade_api

    @property
    def seen_terminal_orders(self) -> set[str]:
        return self._seen_terminal_orders

    async def connect(self) -> None:
        try:
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
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        self._connected = False
        logger.info("okx_broker_disconnected")

    async def submit_order(self, order: OrderAggregate) -> OrderResult:
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
                side=order.side,
            )

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
        if not self._connected or not self._trade_api:
            return False

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._trade_api.cancel_order(
                    instId="",
                    ordId=broker_order_id,  # OKX requires instId but can be empty
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
        if not self._connected or not self._account_api:
            return []

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self._account_api.get_positions())

            if response.get("code") != "0":
                logger.warning("okx_get_positions_failed", error=response.get("msg"))
                return []

            positions = []
            for pos_data in response.get("data", []):
                pos = map_okx_position_to_domain(pos_data, subscription_id="okx")
                if pos:
                    positions.append(pos)

            return positions

        except Exception as e:
            logger.error("okx_get_positions_error", error=str(e))
            return []

    async def get_balance(self) -> AccountBalance:
        if not self._connected or not self._account_api:
            return AccountBalance(total_equity=0, available_balance=0, currency="USDT")

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._account_api.get_account_balance()
            )

            if response.get("code") != "0":
                logger.warning("okx_get_balance_failed", error=response.get("msg"))
                return AccountBalance(total_equity=0, available_balance=0, currency="USDT")

            data = response.get("data", [{}])[0]
            balance_dict = map_okx_balance_to_domain(data)

            return AccountBalance(**balance_dict)

        except Exception as e:
            logger.error("okx_get_balance_error", error=str(e))
            return AccountBalance(total_equity=0, available_balance=0, currency="USDT")

    async def subscribe_order_updates(self, callback: OrderCallback) -> None:
        self._order_callbacks.append(callback)

        if not self._ws_task:
            self._ws_task = asyncio.create_task(self._ws_listener())

    async def unsubscribe_order_updates(self) -> None:
        self._order_callbacks.clear()

        if self._ws_task:
            self._ws_task.cancel()
            self._ws_task = None

    async def _ws_listener(self) -> None:
        """WebSocket listener for order and position updates.

        Connects to OKX private WebSocket, subscribes to orders and positions
        channels, and processes incoming messages. Handles reconnection via
        OkxReconnectionHandler with exponential backoff.
        """
        logger.info("okx_ws_listener_starting")

        try:
            self._ws_client = OkxWebSocketClient(
                api_key=self._api_key,
                api_secret=self._api_secret,
                passphrase=self._passphrase,
                demo=self._demo,
                on_disconnect=self._on_ws_disconnect,
            )

            self._reconnection_handler = OkxReconnectionHandler(
                ws_client=self._ws_client,
                broker=self,
            )

            await self._ws_client.connect()

            await self._ws_client.subscribe(
                [
                    {"channel": "orders", "instType": "SWAP"},
                    {"channel": "positions", "instType": "SWAP"},
                ]
            )

            logger.info("okx_ws_listener_started")

            async for message in self._ws_client:
                await self._handle_ws_message(message)

        except asyncio.CancelledError:
            logger.info("okx_ws_listener_cancelled")
        except ConnectionError as e:
            logger.error("okx_ws_connection_error", error=str(e))
            # Trigger reconnection on connection error
            if self._reconnection_handler and self._connected:
                asyncio.create_task(self._reconnection_handler.handle_disconnect())
        except Exception as e:
            logger.error("okx_ws_listener_error", error=str(e))
        finally:
            if self._reconnection_handler:
                self._reconnection_handler.stop()
                self._reconnection_handler = None
            if self._ws_client:
                await self._ws_client.disconnect()
                self._ws_client = None

    async def _handle_ws_message(self, message: dict) -> None:
        """Handle incoming WebSocket message.

        Routes messages to appropriate handlers based on channel.
        """
        channel, data_items = OkxMessageParser.parse(message)

        if channel == "orders":
            for item in data_items:
                await self._handle_order_update(item)
        elif channel == "positions":
            for item in data_items:
                await self._handle_position_update(item)

    async def _handle_order_update(self, data: dict) -> None:
        """Handle order channel update.

        Deduplicates terminal states and triggers callbacks.
        """
        ord_id = OkxOrderMapper.get_order_id(data)
        state = OkxOrderMapper.get_state(data)

        # Deduplicate terminal states (filled, canceled)
        if OkxOrderMapper.is_terminal(state):
            if ord_id in self._seen_terminal_orders:
                logger.debug("okx_order_duplicate_terminal", ord_id=ord_id, state=state)
                return
            self._seen_terminal_orders.add(ord_id)

        result = OkxOrderMapper.to_order_result(data)

        logger.info(
            "okx_order_update",
            order_id=result.order_id,
            broker_order_id=result.broker_order_id,
            status=result.status.value,
            filled_qty=result.filled_quantity,
        )

        await self._notify_callbacks(result)

    async def _handle_position_update(self, data: dict) -> None:
        """Handle position channel update.

        Logs position changes for monitoring.
        Future: Could emit PositionUpdatedEvent via EventBus.
        """
        position = OkxPositionMapper.to_position_update(data)

        logger.info(
            "okx_position_update",
            position_id=position.position_id,
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity,
            unrealized_pnl=position.unrealized_pnl,
        )

    def _on_ws_disconnect(self) -> None:
        logger.warning("okx_ws_disconnected_callback")

        if self._reconnection_handler and self._connected:
            asyncio.create_task(self._reconnection_handler.handle_disconnect())

    async def _notify_callbacks(self, result: OrderResult) -> None:
        """Notify all registered callbacks of order update.

        NOTE: Callback errors are re-raised after logging. If callbacks must not
        break the broker, the caller should handle exceptions appropriately.
        """
        errors: list[Exception] = []
        for callback in self._order_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except Exception as e:
                logger.warning("okx_callback_error", error=str(e))
                errors.append(e)

        if errors:
            # NOTE: Re-raising first error after all callbacks attempted.
            # This ensures all callbacks get notified while still surfacing failures.
            raise errors[0]
