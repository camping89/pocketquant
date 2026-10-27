"""Order manager - handles order lifecycle and broker submission."""

import asyncio

import structlog

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.brokers.broker_port import IBrokerPort
from pocketquant.core.domain.brokers.value_objects import OrderResult
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderStatus,
)
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository

logger = structlog.get_logger(__name__)


class OrderAppService:
    """Manages order lifecycle from creation to completion.

    Responsibilities:
    - Submit orders to brokers
    - Track order status
    - Publish order events
    - Apply broker fill and cancel callbacks
    """

    def __init__(self, event_bus: EventBus, order_repository: OrderRepository) -> None:
        self._event_bus = event_bus
        self._order_repo = order_repository
        self._pending: dict[str, OrderAggregate] = {}
        self._lock = asyncio.Lock()

    async def submit(self, order: OrderAggregate, broker: IBrokerPort) -> OrderResult:
        """Submit order to broker and track status.

        Args:
            order: Order to submit
            broker: Broker to submit to

        Returns:
            OrderResult from broker
        """
        async with self._lock:
            self._pending[str(order.id)] = order

        await self._order_repo.save(order)

        try:
            result = await broker.submit_order(order)
        except Exception as e:
            async with self._lock:
                order.reject(str(e))
                await self._order_repo.save(order)
                self._pending.pop(str(order.id), None)

            logger.error("order_submit_error", order_id=str(order.id), error=str(e))

            return OrderResult(
                order_id=str(order.id),
                broker_order_id="",
                status=OrderStatus.REJECTED,
                error_message=str(e),
            )

        try:
            async with self._lock:
                if result.is_success:
                    order.broker_order_id = result.broker_order_id

                    if result.status == OrderStatus.FILLED:
                        # An immediate fill still has to pass through SUBMITTED:
                        # the state machine forbids PENDING→FILLED directly, so
                        # without this the fill raised and the order was wrongly
                        # rejected (entry OrderFilledEvent never published).
                        if order.status == OrderStatus.PENDING:
                            order.submit(result.broker_order_id)
                        order.fill(result.filled_quantity, result.filled_price or 0.0)

                        self._pending.pop(str(order.id), None)

                        await self._save_after_fill(order)

                        await self._event_bus.publish(
                            OrderFilledEvent(
                                order_id=str(order.id),
                                subscription_id=order.subscription_id,
                                symbol=order.symbol,
                                side=order.side,
                                filled_quantity=result.filled_quantity,
                                filled_price=result.filled_price or 0.0,
                            )
                        )

                        logger.info(
                            "order_filled",
                            order_id=str(order.id),
                            subscription_id=order.subscription_id,
                            filled_price=result.filled_price,
                        )
                    else:
                        order.submit(result.broker_order_id)
                        await self._order_repo.save(order)

                        logger.info(
                            "order_submitted",
                            order_id=str(order.id),
                            broker_order_id=result.broker_order_id,
                            status=result.status.value,
                        )
                else:
                    order.reject(result.error_message or "Order rejected")
                    await self._order_repo.save(order)

                    self._pending.pop(str(order.id), None)
                    logger.warning(
                        "order_rejected",
                        order_id=str(order.id),
                        error=result.error_message,
                    )

        except Exception:
            # The broker already took the order, so it is never rejected here: a
            # failed save or fill handler is logged and the broker's result stands.
            logger.error(
                "order_post_submit_error",
                order_id=str(order.id),
                status=order.status.value,
                exc_info=True,
            )

        return result

    async def _save_after_fill(self, order: OrderAggregate) -> None:
        """Save a filled order; a failed save is logged so the fill event still goes out."""
        try:
            await self._order_repo.save(order)
        except Exception:
            logger.error("order_save_failed", order_id=str(order.id), exc_info=True)

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
                await self._save_after_fill(order)

                self._pending.pop(result.order_id, None)

                await self._event_bus.publish(
                    OrderFilledEvent(
                        order_id=str(order.id),
                        subscription_id=order.subscription_id,
                        symbol=order.symbol,
                        side=order.side,
                        filled_quantity=result.filled_quantity,
                        filled_price=result.filled_price or 0.0,
                    )
                )

            elif result.status == OrderStatus.CANCELLED:
                order.cancel()
                await self._order_repo.save(order)
                self._pending.pop(result.order_id, None)

                await self._event_bus.publish(
                    OrderCancelledEvent(
                        order_id=result.order_id,
                        subscription_id=order.subscription_id,
                        reason=result.error_message or "",
                    )
                )

    async def load_pending_orders(self) -> None:
        pending = await self._order_repo.find_pending()
        async with self._lock:
            for order in pending:
                self._pending[str(order.id)] = order
        logger.info("loaded_pending_orders", count=len(pending))
