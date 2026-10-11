"""Per-exchange sync policy and the registry that resolves a composite symbol by its suffix.

Each policy carries its own data and quote provider. There is no fallback: a symbol whose
exchange suffix has no policy is unknown, logged once per exchange and skipped by callers.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.market_data.interfaces import IDataProvider, IRealtimeQuoteProvider
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.entities import split_composite

logger = get_logger(__name__)

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _week_minute(text: str, *, round_up: bool) -> int:
    day, clock = (part.strip() for part in text.split(","))
    hours, minutes, seconds = (int(x) for x in clock.split(":"))
    minute = _WEEKDAYS.index(day) * 1440 + hours * 60 + minutes
    return minute + 1 if round_up and seconds else minute


@dataclass(frozen=True)
class MarketCalendar:
    """Weekly trading sessions as ``[start, end)`` minute-of-week pairs; ``None`` is always open."""

    sessions: tuple[tuple[int, int], ...] | None = None

    @classmethod
    def from_week_sessions(cls, sessions: Sequence[Mapping[str, str]]) -> MarketCalendar:
        return cls(
            sessions=tuple(
                (
                    _week_minute(s["week_start_time"], round_up=False),
                    _week_minute(s["week_end_time"], round_up=True),
                )
                for s in sessions
                if s.get("trade_mode", "enabled") == "enabled"
            )
        )

    def is_open(self, ts: datetime) -> bool:
        if self.sessions is None:
            return True
        utc = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
        minute = utc.weekday() * 1440 + utc.hour * 60 + utc.minute
        # A session whose end precedes its start wraps across the Sunday → Monday boundary.
        return any(
            start <= minute < end if start <= end else (minute >= start or minute < end)
            for start, end in self.sessions
        )


ALWAYS_OPEN = MarketCalendar()


@dataclass(frozen=True)
class SyncPolicy:
    exchange: str
    data_provider: IDataProvider
    quote_provider: IRealtimeQuoteProvider | None
    poll_intervals: tuple[Interval, ...]
    poll_n_bars: int
    cascade: bool
    cascade_lookback_minutes: int
    integrity_intervals: tuple[Interval, ...]
    backfill_n_bars: int
    poll_time_cap_s: float | None = None
    history_days: Mapping[Interval, int | None] = field(default_factory=dict)
    calendars: Mapping[str, MarketCalendar] = field(default_factory=dict)


class SyncPolicies:
    def __init__(self, policies: Iterable[SyncPolicy]) -> None:
        self._by_exchange = {p.exchange: p for p in policies}
        self._warned: set[str] = set()

    def __iter__(self) -> Iterator[SyncPolicy]:
        return iter(self._by_exchange.values())

    def policy_for(self, symbol: str) -> SyncPolicy | None:
        exchange = split_composite(symbol)[1]
        policy = self._by_exchange.get(exchange)
        if policy is None and exchange not in self._warned:
            self._warned.add(exchange)
            logger.warning("market_data.unknown_exchange", exchange=exchange, symbol=symbol.upper())
        return policy

    def market_calendar(self, symbol: str) -> MarketCalendar:
        policy = self.policy_for(symbol)
        if policy is None:
            return ALWAYS_OPEN
        return policy.calendars.get(split_composite(symbol)[0], ALWAYS_OPEN)

    def quote_providers(self) -> list[IRealtimeQuoteProvider]:
        return [p.quote_provider for p in self if p.quote_provider is not None]


def binance_policy(
    data_provider: IDataProvider,
    quote_provider: IRealtimeQuoteProvider | None,
) -> SyncPolicy:
    # 1m polled over REST, 5m–1d cascaded from 1m, 1w synced over REST: Binance serves
    # Monday-aligned weekly klines, while cascading from 1m would bucket weeks on Thursday.
    return SyncPolicy(
        exchange="BINANCE",
        data_provider=data_provider,
        quote_provider=quote_provider,
        poll_intervals=(Interval.MINUTE_1,),
        poll_n_bars=100,
        cascade=True,
        cascade_lookback_minutes=100,
        integrity_intervals=(
            Interval.MINUTE_1,
            Interval.MINUTE_5,
            Interval.MINUTE_15,
            Interval.HOUR_1,
            Interval.HOUR_4,
            Interval.DAY_1,
            Interval.WEEK_1,
        ),
        backfill_n_bars=5000,
    )
