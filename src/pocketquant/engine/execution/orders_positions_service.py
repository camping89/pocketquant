"""Orders + positions query service — reads live in-RAM engine state.

These queries depend on OrderAppService / PositionAppService which hold live
in-RAM state — they answer from the running execution engine, not the DB.
"""

from __future__ import annotations

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService


class OrderPositionQueryService:
    """Read live in-RAM order and position state from the execution engine.

    Requires OrderAppService / PositionAppService — answers reflect the
    running engine, not persisted DB rows.
    """

    def __init__(
        self,
        order_app_service: OrderAppService,
        position_app_service: PositionAppService,
    ) -> None:
        self._orders = order_app_service
        self._positions = position_app_service

    async def get_order(self, order_id: str) -> dict:
        order = self._orders.get_order(order_id)
        if not order:
            raise NotFoundError(f"Order not found: {order_id}")
        return {
            "id": str(order.id),
            "subscription_id": order.subscription_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "price": order.price,
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "filled_price": order.filled_price,
        }

    async def list_orders(self) -> list[dict]:
        pending = self._orders.get_pending_orders()
        filled = self._orders.get_filled_orders()
        return [
            {
                "id": str(o.id),
                "subscription_id": o.subscription_id,
                "symbol": o.symbol,
                "side": o.side.value,
                "order_type": o.order_type.value,
                "quantity": o.quantity,
                "price": o.price,
                "status": o.status.value,
                "filled_quantity": o.filled_quantity,
                "filled_price": o.filled_price,
            }
            for o in pending + filled
        ]

    async def get_position(self, strategy_id: str) -> dict:
        summary = self._positions.get_position_summary(strategy_id)
        if not summary:
            raise NotFoundError(f"No position for strategy: {strategy_id}")
        return summary

    async def list_positions(self) -> list[dict]:
        return self._positions.get_all_summaries()
