from dataclasses import dataclass

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
