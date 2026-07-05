from dataclasses import dataclass
from datetime import datetime

from pocketquant.core.domain.position.enums import PositionSide
from pocketquant.core.domain.shared.events import DomainEvent


@dataclass(frozen=True, eq=False)
class PositionOpenedEvent(DomainEvent):
    position_id: str = ""
    subscription_id: str = ""
    symbol: str = ""
    side: PositionSide = PositionSide.LONG
    entry_price: float = 0.0
    quantity: float = 0.0


@dataclass(frozen=True, eq=False)
class PositionUpdatedEvent(DomainEvent):
    position_id: str = ""
    subscription_id: str = ""
    quantity: float = 0.0
    average_price: float = 0.0
    unrealized_pnl: float = 0.0


@dataclass(frozen=True, eq=False)
class PositionClosedEvent(DomainEvent):
    position_id: str = ""
    subscription_id: str = ""
    symbol: str = ""
    side: PositionSide = PositionSide.LONG
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    realized_pnl: float = 0.0


@dataclass(frozen=True, eq=False)
class TradeClosedEvent(DomainEvent):
    """Round-trip chunk closed on a position reduce/close.

    Economic-only: carries no run_id/strategy_code (broker layer back-links those).
    ``pnl`` is the realized delta of THIS chunk (not cumulative); ``commission`` is
    the entry portion for the chunk plus its exit commission.
    """

    position_id: str = ""
    subscription_id: str = ""
    symbol: str = ""
    direction: str = "LONG"
    entry_order_id: str | None = None
    entry_price: float = 0.0
    entry_time: datetime | None = None
    quantity: float = 0.0
    exit_order_id: str | None = None
    exit_price: float = 0.0
    exit_time: datetime | None = None
    sl_price: float | None = None
    tp_price: float | None = None
    pnl: float = 0.0
    commission: float = 0.0
    duration_seconds: float = 0.0
