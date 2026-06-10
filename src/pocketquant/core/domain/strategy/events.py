"""Strategy domain events."""

from dataclasses import dataclass

from pocketquant.core.domain.shared.events import DomainEvent
from pocketquant.core.domain.strategy.enums import Direction


@dataclass(frozen=True, eq=False)
class SignalGeneratedEvent(DomainEvent):
    """Event raised when a strategy generates a trading signal."""

    subscription_id: str = ""
    symbol: str = ""
    direction: Direction = Direction.FLAT
    confidence: float = 0.0
    entry_price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
