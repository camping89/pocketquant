"""List orders handler."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.execution.app_services.order_app_service import OrderAppService
from pocketquant.trading.handlers.trading.list_orders.query import ListOrdersQuery


@handles(ListOrdersQuery)
class ListOrdersHandler(Handler[ListOrdersQuery, list[dict]]):
    def __init__(self, order_app_service: OrderAppService):
        self._order_app_service = order_app_service

    async def handle(self, request: ListOrdersQuery) -> list[dict]:
        pending = self._order_app_service.get_pending_orders()
        filled = self._order_app_service.get_filled_orders()

        return [
            {
                "id": o.id,
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
