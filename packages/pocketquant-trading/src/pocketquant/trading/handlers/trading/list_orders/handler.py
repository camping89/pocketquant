"""List orders handler."""

from pocketquant.trading.app_services.order_app_service import OrderAppService
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.trading.list_orders.query import ListOrdersQuery


@handles(ListOrdersQuery)
class ListOrdersHandler(Handler[ListOrdersQuery, list[dict]]):
    """Handler to list all orders."""

    def __init__(self, order_app_service: OrderAppService):
        self._order_app_service = order_app_service

    async def handle(self, request: ListOrdersQuery) -> list[dict]:
        """Get all orders (pending + filled)."""
        pending = self._order_app_service.get_pending_orders()
        filled = self._order_app_service.get_filled_orders()

        return [
            {
                "id": o.id,
                "strategy_id": o.strategy_id,
                "symbol": o.symbol,
                "exchange": o.exchange,
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
