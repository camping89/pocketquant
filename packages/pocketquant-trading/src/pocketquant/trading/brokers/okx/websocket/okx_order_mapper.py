"""OKX order mapper - converts WebSocket order messages to domain models."""

from typing import Any

from pocketquant.core.domain.order import OrderStatus
from pocketquant.core.domain.brokers.value_objects import OrderResult

# OKX order state to domain OrderStatus mapping
OKX_STATE_MAP: dict[str, OrderStatus] = {
    "live": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "mmp_canceled": OrderStatus.CANCELLED,  # Market maker protection
}

# Terminal states that should only be processed once
TERMINAL_STATES = frozenset({"filled", "canceled", "mmp_canceled"})


class OkxOrderMapper:
    """Map OKX WebSocket order messages to domain OrderResult."""

    @staticmethod
    def to_order_result(data: dict[str, Any]) -> OrderResult:
        """Convert OKX order update to OrderResult.

        Args:
            data: Single order item from OKX orders channel.

        Returns:
            OrderResult with mapped status and fill information.

        OKX order data fields:
        - ordId: OKX order ID (broker_order_id)
        - clOrdId: Client order ID (our order.id)
        - state: Order state (live, filled, canceled, etc.)
        - accFillSz: Accumulated fill size
        - avgPx: Average fill price
        - sz: Order size
        """
        state = data.get("state", "")
        status = OKX_STATE_MAP.get(state, OrderStatus.PENDING)

        acc_fill_sz = data.get("accFillSz", "0")
        avg_px = data.get("avgPx", "")

        filled_quantity = float(acc_fill_sz) if acc_fill_sz else 0.0
        filled_price = float(avg_px) if avg_px else None

        order_id = data.get("clOrdId", "")  # Our client order ID
        broker_order_id = data.get("ordId", "")  # OKX order ID

        # Error message if any
        error_msg = data.get("msg") if data.get("sCode") != "0" else None

        return OrderResult(
            order_id=order_id,
            broker_order_id=broker_order_id,
            status=status,
            filled_quantity=filled_quantity,
            filled_price=filled_price,
            error_message=error_msg,
        )

    @staticmethod
    def is_terminal(state: str) -> bool:
        """Check if order state is terminal (filled, canceled).

        Terminal states should only be processed once to avoid
        duplicate callbacks.
        """
        return state in TERMINAL_STATES

    @staticmethod
    def get_order_id(data: dict[str, Any]) -> str:
        return data.get("ordId", "")

    @staticmethod
    def get_client_order_id(data: dict[str, Any]) -> str:
        return data.get("clOrdId", "")

    @staticmethod
    def get_state(data: dict[str, Any]) -> str:
        return data.get("state", "")

    @staticmethod
    def get_symbol(data: dict[str, Any]) -> str:
        """Get trading symbol from instId — strips -SWAP suffix and dashes."""
        inst_id = data.get("instId", "")
        return inst_id.replace("-SWAP", "").replace("-", "")

    @staticmethod
    def get_side(data: dict[str, Any]) -> str:
        return data.get("side", "").upper()
