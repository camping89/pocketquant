"""OHLCV aggregate root — Pydantic model (in-memory only, not persisted)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from src.common.uuid import UUID, generate_id
from src.domain.ohlcv.ohlcv_event import BarCompletedEvent, HistoricalDataSyncedEvent
from src.domain.shared.domain_event import DomainEvent
from src.domain.shared.value_objects import Interval


class OHLCVAggregate(BaseModel):
    """Aggregate root for OHLCV data operations."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    symbol: str = ""
    exchange: str = ""
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

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
        event = HistoricalDataSyncedEvent(
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
        event = BarCompletedEvent(
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
