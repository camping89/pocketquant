"""OKX position mapper - converts WebSocket position messages to domain models."""

from dataclasses import dataclass
from typing import Any


@dataclass
class PositionUpdate:
    """Position update from OKX WebSocket.

    Represents current position state for a symbol.
    """

    position_id: str
    symbol: str
    side: str  # "long" or "short"
    quantity: float
    entry_price: float
    unrealized_pnl: float
    mark_price: float
    leverage: float
    margin_mode: str  # "cross" or "isolated"

    @property
    def is_open(self) -> bool:
        return self.quantity > 0


class OkxPositionMapper:
    """Map OKX WebSocket position messages to PositionUpdate."""

    @staticmethod
    def to_position_update(data: dict[str, Any]) -> PositionUpdate:
        """Convert OKX position update to PositionUpdate.

        Args:
            data: Single position item from OKX positions channel.

        Returns:
            PositionUpdate with position details.

        OKX position data fields:
        - posId: Position ID
        - instId: Instrument ID (e.g., "BTC-USDT-SWAP")
        - posSide: Position side (long/short/net)
        - pos: Position size (can be negative for short)
        - avgPx: Average entry price
        - upl: Unrealized PnL
        - markPx: Mark price
        - lever: Leverage
        - mgnMode: Margin mode (cross/isolated)
        """
        pos_str = data.get("pos", "0")
        pos_float = float(pos_str) if pos_str else 0.0

        # Determine side from posSide or sign of position
        pos_side = data.get("posSide", "net")
        if pos_side == "net":
            side = "long" if pos_float >= 0 else "short"
        else:
            side = pos_side

        quantity = abs(pos_float)

        avg_px = data.get("avgPx", "0")
        upl = data.get("upl", "0")
        mark_px = data.get("markPx", "0")
        lever = data.get("lever", "1")

        inst_id = data.get("instId", "")
        symbol = inst_id.replace("-SWAP", "").replace("-", "")

        return PositionUpdate(
            position_id=data.get("posId", ""),
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=float(avg_px) if avg_px else 0.0,
            unrealized_pnl=float(upl) if upl else 0.0,
            mark_price=float(mark_px) if mark_px else 0.0,
            leverage=float(lever) if lever else 1.0,
            margin_mode=data.get("mgnMode", "cross"),
        )

    @staticmethod
    def get_position_id(data: dict[str, Any]) -> str:
        return data.get("posId", "")

    @staticmethod
    def get_inst_id(data: dict[str, Any]) -> str:
        return data.get("instId", "")

    @staticmethod
    def is_position_closed(data: dict[str, Any]) -> bool:
        pos = data.get("pos", "0")
        return float(pos) == 0.0 if pos else True
