"""Get order handler."""

from fastapi import HTTPException

from src.common.mediator import Handler
from src.features.trading.base.managers.order_manager import OrderManager
from src.features.trading.get_order.query import GetOrderQuery


class GetOrderHandler(Handler[GetOrderQuery, dict]):
    """Handler to get a specific order."""

    def __init__(self, order_manager: OrderManager):
        self.order_manager = order_manager

    async def handle(self, request: GetOrderQuery) -> dict:
        """Get order by ID."""
        order = self.order_manager.get_order(request.order_id)

        if not order:
            raise HTTPException(
                status_code=404, detail=f"Order not found: {request.order_id}"
            )

        return {
            "id": order.id,
            "strategy_id": order.strategy_id,
            "symbol": order.symbol,
            "exchange": order.exchange,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "price": order.price,
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "filled_price": order.filled_price,
        }
