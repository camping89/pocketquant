"""Order manager - handles order lifecycle and broker submission."""

import asyncio

import structlog

from src.common.messaging import EventBus
from src.domain.order import OrderAggregate, OrderFilledEvent, OrderStatus
from src.infrastructure.brokers import IBroker, OrderResult
from src.persistence.repositories.order_repository import OrderRepository

logger = structlog.get_logger(__name__)


class OrderAppService:
    """Manages order lifecycle from creation to completion.

    Responsibilities:
    - Submit orders to brokers
    - Track order status
    - Publish order events
    - Handle order cancellation
    """

    def __init__(self, event_bus: EventBus, order_repository: OrderRepository) -> None:
        self._event_bus = event_bus
        self._order_repo = order_repository
        self._orders: dict[str, OrderAggregate] = {}
        self._pending: dict[str, OrderAggregate] = {}
        self._broker_map: dict[str, str] = {}  # order_id -> broker_order_id
        self._lock = asyncio.Lock()

    async def submit(self, order: OrderAggregate, broker: IBroker) -> OrderResult:
        """Submit order to broker and track status.

        Args:
            order: Order to submit
            broker: Broker to submit to

        Returns:
            OrderResult from broker
        """
        async with self._lock:
            self._pending[order.id] = order

        # Persist initial order state
        await self._order_repo.save(order)

        try:
            result = await broker.submit_order(order)

            async with self._lock:
                if result.is_success:
                    self._broker_map[order.id] = result.broker_order_id
                    order.broker_order_id = result.broker_order_id

                    if result.status == OrderStatus.FILLED:
                        # Update order with fill info
                        order.fill(result.filled_quantity, result.filled_price or 0.0)

                        # Move to completed orders
                        self._orders[order.id] = order
                        self._pending.pop(order.id, None)

                        # Persist filled order
                        await self._order_repo.save(order)

                        # Publish fill event
                        await self._event_bus.publish(
                            OrderFilledEvent(
                                order_id=order.id,
                                strategy_id=order.strategy_id,
                                symbol=order.symbol,
                                exchange=order.exchange,
                                side=order.side,
                                filled_quantity=result.filled_quantity,
                                filled_price=result.filled_price or 0.0,
                            )
                        )

                        logger.info(
                            "order_filled",
                            order_id=order.id,
                            strategy_id=order.strategy_id,
                            filled_price=result.filled_price,
                        )
                    else:
                        # Update status and persist
                        order.submit(result.broker_order_id)
                        await self._order_repo.save(order)

                        logger.info(
                            "order_submitted",
                            order_id=order.id,
                            broker_order_id=result.broker_order_id,
                            status=result.status.value,
                        )
                else:
                    # Mark as rejected and persist
                    order.reject(result.error_message or "Order rejected")
                    await self._order_repo.save(order)

                    self._pending.pop(order.id, None)
                    logger.warning(
                        "order_rejected",
                        order_id=order.id,
                        error=result.error_message,
                    )

            return result

        except Exception as e:
            async with self._lock:
                order.reject(str(e))
                await self._order_repo.save(order)
                self._pending.pop(order.id, None)

            logger.error("order_submit_error", order_id=order.id, error=str(e))

            return OrderResult(
                order_id=order.id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                error_message=str(e),
            )

    async def cancel(self, order_id: str, broker: IBroker) -> bool:
        """Cancel an order.

        Args:
            order_id: Internal order ID
            broker: Broker to cancel on

        Returns:
            True if cancellation was successful
        """
        async with self._lock:
            broker_order_id = self._broker_map.get(order_id)
            order = self._pending.get(order_id)
            if not broker_order_id:
                logger.warning("cancel_unknown_order", order_id=order_id)
                return False

        try:
            success = await broker.cancel_order(broker_order_id)

            if success:
                async with self._lock:
                    if order:
                        order.cancel()
                        await self._order_repo.save(order)
                    self._pending.pop(order_id, None)

                logger.info("order_cancelled", order_id=order_id)

            return success

        except Exception as e:
            logger.error("order_cancel_error", order_id=order_id, error=str(e))
            return False

    def get_order(self, order_id: str) -> OrderAggregate | None:
        """Get order by ID."""
        return self._orders.get(order_id) or self._pending.get(order_id)

    def get_pending_orders(self) -> list[OrderAggregate]:
        """Get all pending orders."""
        return list(self._pending.values())

    def get_filled_orders(self) -> list[OrderAggregate]:
        """Get all filled orders."""
        return list(self._orders.values())

    def get_orders_by_strategy(self, strategy_id: str) -> list[OrderAggregate]:
        """Get all orders for a strategy."""
        all_orders = list(self._orders.values()) + list(self._pending.values())
        return [o for o in all_orders if o.strategy_id == strategy_id]

    async def on_order_update(self, result: OrderResult) -> None:
        """Handle order update from broker callback.

        Called by broker WebSocket when order status changes.
        """
        async with self._lock:
            order = self._pending.get(result.order_id)
            if not order:
                return

            if result.status == OrderStatus.FILLED:
                order.fill(result.filled_quantity, result.filled_price or 0.0)
                await self._order_repo.save(order)

                self._orders[result.order_id] = order
                self._pending.pop(result.order_id, None)

                await self._event_bus.publish(
                    OrderFilledEvent(
                        order_id=order.id,
                        strategy_id=order.strategy_id,
                        symbol=order.symbol,
                        exchange=order.exchange,
                        side=order.side,
                        filled_quantity=result.filled_quantity,
                        filled_price=result.filled_price or 0.0,
                    )
                )

            elif result.status == OrderStatus.CANCELLED:
                order.cancel()
                await self._order_repo.save(order)
                self._pending.pop(result.order_id, None)

    async def load_pending_orders(self) -> None:
        """Load pending orders from database on startup."""
        pending = await self._order_repo.find_pending()
        async with self._lock:
            for order in pending:
                self._pending[order.id] = order
                if order.broker_order_id:
                    self._broker_map[order.id] = order.broker_order_id
        logger.info("loaded_pending_orders", count=len(pending))

    async def get_order_async(self, order_id: str) -> OrderAggregate | None:
        """Get order by ID from memory or database."""
        order = self._orders.get(order_id) or self._pending.get(order_id)
        if order:
            return order
        return await self._order_repo.get(order_id)

    async def get_orders_by_strategy_async(self, strategy_id: str) -> list[OrderAggregate]:
        """Get all orders for a strategy from database."""
        return await self._order_repo.find_by_strategy(strategy_id)
