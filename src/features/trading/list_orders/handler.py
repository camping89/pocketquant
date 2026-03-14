"""List orders handler."""

from src.application.trading.order_app_service import OrderAppService
from src.common.mediator import Handler, handles
from src.features.trading.list_orders.query import ListOrdersQuery


@handles(ListOrdersQuery)
class ListOrdersHandler(Handler[ListOrdersQuery, list[dict]]):
    """Handler to list all orders."""

    def __init__(self, order_manager: OrderAppService):
        self.order_manager = order_manager

    async def handle(self, request: ListOrdersQuery) -> list[dict]:
        """Get all orders (pending + filled)."""
        pending = self.order_manager.get_pending_orders()
        filled = self.order_manager.get_filled_orders()

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
