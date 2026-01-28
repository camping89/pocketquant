"""Quote aggregate root."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from src.domain.quote.events import QuoteReceived, QuoteUpdated
from src.domain.shared.events import DomainEvent


@dataclass(eq=False)
class QuoteAggregate:
    """Aggregate root for real-time quote management."""

    id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    exchange: str = ""
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    change: float | None = None
    change_percent: float | None = None
    last_update: datetime | None = None
    _events: list[DomainEvent] = field(default_factory=list)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QuoteAggregate):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @classmethod
    def create(cls, symbol: str, exchange: str) -> QuoteAggregate:
        """Factory method to create a new quote aggregate."""
        return cls(symbol=symbol.upper(), exchange=exchange.upper())

    def update_from_tick(
        self,
        price: float,
        volume: float | None = None,
        bid: float | None = None,
        ask: float | None = None,
        change: float | None = None,
        change_percent: float | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Update quote from incoming tick data."""
        self.last_price = price
        if volume is not None:
            self.volume = volume
        if bid is not None:
            self.bid = bid
        if ask is not None:
            self.ask = ask
        if change is not None:
            self.change = change
        if change_percent is not None:
            self.change_percent = change_percent
        self.last_update = timestamp

        self._events.append(
            QuoteReceived(
                symbol=self.symbol,
                exchange=self.exchange,
                price=price,
                volume=volume,
                timestamp=timestamp,
            )
        )

    def mark_updated(self) -> None:
        """Mark that quote was persisted/cached."""
        self._events.append(
            QuoteUpdated(
                symbol=self.symbol,
                exchange=self.exchange,
                last_price=self.last_price or 0.0,
                change=self.change,
                change_percent=self.change_percent,
            )
        )

    @property
    def symbol_key(self) -> str:
        """Return 'EXCHANGE:SYMBOL' format."""
        return f"{self.exchange}:{self.symbol}"

    def get_uncommitted_events(self) -> list[DomainEvent]:
        return self._events.copy()

    def clear_events(self) -> None:
        self._events.clear()
