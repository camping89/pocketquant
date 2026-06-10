"""OKX API response mappers to domain models."""

from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.position import PositionAggregate, PositionSide


def map_okx_order_state(state: str) -> OrderStatus:
    mapping = {
        "live": OrderStatus.SUBMITTED,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "filled": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELLED,
        "mmp_canceled": OrderStatus.CANCELLED,
    }
    return mapping.get(state, OrderStatus.PENDING)


def map_order_side_to_okx(side: OrderSide) -> str:
    return "buy" if side == OrderSide.BUY else "sell"


def map_order_type_to_okx(order_type: OrderType) -> str:
    mapping = {
        OrderType.MARKET: "market",
        OrderType.LIMIT: "limit",
        OrderType.STOP_LIMIT: "trigger",
        OrderType.STOP_MARKET: "trigger",
    }
    return mapping.get(order_type, "market")


def map_order_to_okx_params(order: OrderAggregate, inst_suffix: str = "USDT") -> dict:
    """Convert domain Order to OKX API parameters.

    Args:
        order: Domain order aggregate
        inst_suffix: Suffix for instrument ID (e.g., "USDT" for spot)

    Returns:
        Dict of OKX API parameters
    """
    params = {
        "instId": f"{order.symbol}-{inst_suffix}",
        "tdMode": "cash",  # cash for spot, cross/isolated for margin
        "side": map_order_side_to_okx(order.side),
        "ordType": map_order_type_to_okx(order.order_type),
        "sz": str(order.quantity),
        "clOrdId": order.id,  # Client order ID for tracking
    }

    if order.order_type == OrderType.LIMIT and order.price:
        params["px"] = str(order.price)

    if order.order_type in (OrderType.STOP_LIMIT, OrderType.STOP_MARKET):
        if order.stop_price:
            params["triggerPx"] = str(order.stop_price)
        if order.price:
            params["orderPx"] = str(order.price)

    return params


def map_okx_position_to_domain(pos_data: dict, subscription_id: str) -> PositionAggregate | None:
    """Map OKX position response to domain PositionAggregate.

    Args:
        pos_data: OKX position data from API
        subscription_id: Subscription ID to associate with position

    Returns:
        PositionAggregate or None if no position
    """
    pos_amt = float(pos_data.get("pos", "0"))
    if pos_amt == 0:
        return None

    avg_px = float(pos_data.get("avgPx", "0"))
    inst_id = pos_data.get("instId", "")

    # Parse instrument ID (e.g., "BTC-USDT-SWAP") and build composite symbol.
    # OKX-specific boundary: compose "{CODE}{QUOTE}:OKX" from instId parts.
    parts = inst_id.split("-")
    code = parts[0] if parts else inst_id
    quote = parts[1] if len(parts) > 1 else "USDT"
    composite_symbol = f"{code}{quote}:OKX"

    side = PositionSide.LONG if pos_amt > 0 else PositionSide.SHORT
    quantity = abs(pos_amt)

    # Note: upl (unrealized P&L) available in pos_data.get("upl", "0")

    position = PositionAggregate.open(
        subscription_id=subscription_id,
        symbol=composite_symbol,
        side=side,
        entry_price=avg_px,
        quantity=quantity,
    )

    # Update with current market price if available
    mark_px = pos_data.get("markPx")
    if mark_px:
        position.update_price(float(mark_px))

    return position


def map_okx_balance_to_domain(balance_data: dict) -> dict:
    """Map OKX balance response to dict.

    Args:
        balance_data: OKX account balance data

    Returns:
        Dict with total_equity, available_balance, currency
    """
    details = balance_data.get("details", [])

    usdt_balance = next(
        (d for d in details if d.get("ccy") == "USDT"),
        {},
    )

    return {
        "total_equity": float(usdt_balance.get("eq", "0")),
        "available_balance": float(usdt_balance.get("availBal", "0")),
        "currency": "USDT",
        "margin_used": float(usdt_balance.get("frozenBal", "0")),
        "unrealized_pnl": float(usdt_balance.get("upl", "0")),
    }
