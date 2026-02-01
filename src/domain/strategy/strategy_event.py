"""Strategy domain events."""

from src.domain.shared.domain_event import DomainEvent
from src.domain.strategy.value_objects import Direction


class SignalGeneratedEvent(DomainEvent):
    """Event raised when a strategy generates a trading signal."""

    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    direction: Direction = Direction.FLAT
    confidence: float = 0.0
    entry_price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
