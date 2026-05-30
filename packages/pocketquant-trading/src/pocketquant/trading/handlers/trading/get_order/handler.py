"""Get order handler."""

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.app_services.order_app_service import OrderAppService
from pocketquant.trading.handlers.trading.get_order.query import GetOrderQuery


@handles(GetOrderQuery)
class GetOrderHandler(Handler[GetOrderQuery, dict]):
    def __init__(self, order_app_service: OrderAppService):
        self._order_app_service = order_app_service

    async def handle(self, request: GetOrderQuery) -> dict:
        order = self._order_app_service.get_order(request.order_id)

        if not order:
            raise NotFoundError(f"Order not found: {request.order_id}")

        return {
            "id": order.id,
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
