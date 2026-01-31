"""Trading API routes for orders and positions."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/trading", tags=["trading"])


class OrderResponse(BaseModel):
    """Order information response."""

    id: str
    strategy_id: str
    symbol: str
    exchange: str
    side: str
    order_type: str
    quantity: float
    price: float | None
    status: str


class PositionResponse(BaseModel):
    """Position information response."""

    id: str
    strategy_id: str
    symbol: str
    exchange: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float


@router.get("/orders")
async def list_orders(request: Request) -> list[dict]:
    """Get all orders."""
    order_manager = request.app.state.order_manager

    pending = order_manager.get_pending_orders()
    filled = order_manager.get_filled_orders()

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


@router.get("/orders/{order_id}")
async def get_order(order_id: str, request: Request) -> dict:
    """Get a specific order."""
    order_manager = request.app.state.order_manager
    order = order_manager.get_order(order_id)

    if not order:
        raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")

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


@router.get("/positions")
async def list_positions(request: Request) -> list[dict]:
    """Get all open positions."""
    position_tracker = request.app.state.position_tracker
    return position_tracker.get_all_summaries()


@router.get("/positions/{strategy_id}")
async def get_position(strategy_id: str, request: Request) -> dict:
    """Get position for a specific strategy."""
    position_tracker = request.app.state.position_tracker
    summary = position_tracker.get_position_summary(strategy_id)

    if not summary:
        raise HTTPException(
            status_code=404, detail=f"No position for strategy: {strategy_id}"
        )

    return summary
