from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS

if TYPE_CHECKING:
    from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort


def get_bar_start(timestamp: datetime, interval: Interval) -> datetime:
    if timestamp.tzinfo is None:
        raise ValueError("get_bar_start requires a timezone-aware datetime")

    seconds = INTERVAL_SECONDS[interval]

    if interval == Interval.DAY_1:
        return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

    if interval == Interval.WEEK_1:
        # Weekly bars open Monday 00:00 UTC (Binance convention). A plain
        # floor(epoch / 604800) lands on Thursday because the Unix epoch
        # (1970-01-01) was a Thursday — that would make every weekly bar fail
        # is_bar_aligned and get purged by the integrity/repair job.
        midnight = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - timedelta(days=midnight.weekday())

    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    total_seconds = (timestamp - epoch).total_seconds()
    aligned_seconds = (total_seconds // seconds) * seconds

    return epoch + timedelta(seconds=aligned_seconds)


# The grid belongs to the calendar, not the clock: a session opening at 22:00 UTC puts
# hourly bars on another grid. Continuous24x7Calendar delegates to get_bar_start.
def is_bar_aligned(timestamp: datetime, interval: Interval, calendar: ITradingCalendarPort) -> bool:
    return timestamp == calendar.bar_start(timestamp, interval)


def filter_aligned_bars(
    bars: list[Bar], interval: Interval, calendar: ITradingCalendarPort
) -> tuple[list[Bar], list[Bar]]:
    aligned, misaligned = [], []
    for bar in bars:
        if bar.datetime and is_bar_aligned(bar.datetime, interval, calendar):
            aligned.append(bar)
        else:
            misaligned.append(bar)
    return aligned, misaligned


@dataclass
class BarBuilderDomainService:
    symbol: str
    interval: Interval
    bar_start: datetime
    bar_end: datetime | None = None

    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float = 0.0
    tick_count: int = 0
    last_tick_at: datetime | None = None
    gap: bool = False
    # The time from which this bucket's ticks are covered.
    coverage_start: datetime | None = None

    def __post_init__(self) -> None:
        if self.bar_end is None:
            self.bar_end = self.bar_start + timedelta(seconds=INTERVAL_SECONDS[self.interval])

    # volume must be a per-tick delta; a cumulative session total inflates bar volume.
    # False when the tick is outside the bar range (no state change).
    def add_tick(self, price: float, volume: float | None, timestamp: datetime) -> bool:
        if self.bar_end is None or timestamp < self.bar_start or timestamp >= self.bar_end:
            return False

        if self.open is None:
            self.open = price

        if self.high is None or price > self.high:
            self.high = price

        if self.low is None or price < self.low:
            self.low = price

        self.close = price

        if volume is not None:
            self.volume += volume

        self.tick_count += 1
        self.last_tick_at = timestamp
        return True

    def is_empty(self) -> bool:
        return self.tick_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "interval": self.interval.value,
            "bar_start": self.bar_start.isoformat(),
            "bar_end": self.bar_end.isoformat() if self.bar_end else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
            "gap": self.gap,
            "coverage_start": self.coverage_start.isoformat() if self.coverage_start else None,
        }
