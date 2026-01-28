"""OHLCV aggregate root."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from src.domain.ohlcv.events import BarCompleted, HistoricalDataSynced
from src.domain.shared.events import DomainEvent
from src.domain.shared.value_objects import Interval


@dataclass(eq=False)
class OHLCVAggregate:
    """Aggregate root for OHLCV data operations."""

    id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    exchange: str = ""
    _events: list[DomainEvent] = field(default_factory=list)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OHLCVAggregate):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @classmethod
    def create(cls, symbol: str, exchange: str) -> OHLCVAggregate:
        """Factory method to create a new aggregate."""
        return cls(symbol=symbol.upper(), exchange=exchange.upper())

    def record_sync(
        self,
        interval: Interval,
        bars_count: int,
        first_bar_at: datetime | None = None,
        last_bar_at: datetime | None = None,
    ) -> None:
        """Record that historical data was synced."""
        event = HistoricalDataSynced(
            symbol=self.symbol,
            exchange=self.exchange,
            interval=interval.value,
            bars_count=bars_count,
            first_bar_at=first_bar_at,
            last_bar_at=last_bar_at,
        )
        self._events.append(event)

    def record_bar_completed(
        self,
        interval: Interval,
        bar_start: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        tick_count: int,
    ) -> None:
        """Record that a bar was completed."""
        event = BarCompleted(
            symbol=self.symbol,
            exchange=self.exchange,
            interval=interval.value,
            bar_start=bar_start,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            tick_count=tick_count,
        )
        self._events.append(event)

    def get_uncommitted_events(self) -> list[DomainEvent]:
        """Get events that haven't been published yet."""
        return self._events.copy()

    def clear_events(self) -> None:
        """Clear uncommitted events after they've been published."""
        self._events.clear()
