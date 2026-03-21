"""Trading feature router aggregation."""

from fastapi import APIRouter

from pocketquant.trading.handlers.trading.get_order.route import router as get_order_router
from pocketquant.trading.handlers.trading.get_position.route import router as get_position_router
from pocketquant.trading.handlers.trading.list_orders.route import router as list_orders_router
from pocketquant.trading.handlers.trading.list_positions.route import router as list_positions_router

router = APIRouter(prefix="/trading", tags=["trading"])

router.include_router(list_orders_router)
router.include_router(get_order_router)
router.include_router(list_positions_router)
router.include_router(get_position_router)
