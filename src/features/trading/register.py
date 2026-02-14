"""Auto-register all trading CQRS handlers with mediator."""

from src.application.trading.order_manager import OrderManager
from src.application.trading.position_tracker import PositionTracker
from src.common.mediator import HandlerRegistry, Mediator
from src.features.trading.get_order.handler import GetOrderHandler
from src.features.trading.get_position.handler import GetPositionHandler
from src.features.trading.list_orders.handler import ListOrdersHandler
from src.features.trading.list_positions.handler import ListPositionsHandler


def register_handlers(
    mediator: Mediator,
    order_manager: OrderManager,
    position_tracker: PositionTracker,
) -> None:
    """Register all trading handlers with mediator."""
    registry = HandlerRegistry()
    registry.register_all(
        mediator,
        [
            ListOrdersHandler(order_manager),
            GetOrderHandler(order_manager),
            ListPositionsHandler(position_tracker),
            GetPositionHandler(position_tracker),
        ],
    )
