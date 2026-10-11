"""Pin suffix-only policy lookup, the Binance policy values and the session-calendar maths."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import structlog
from structlog.testing import capture_logs

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.entities import split_composite
from pocketquant.engine.market_data import sync_policy
from pocketquant.engine.market_data.sync_policy import (
    ALWAYS_OPEN,
    MarketCalendar,
    SyncPolicies,
    binance_policy,
)

# 2026-10-05 is a Monday.
MON = 5
FRI = 9
SAT = 10
SUN = 11


@pytest.fixture(autouse=True)
def _fresh_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    # cache_logger_on_first_use=True pins an already-used logger's processors, so a logger
    # that emitted in an earlier test would ignore capture_logs without this rebind.
    monkeypatch.setattr(sync_policy, "logger", structlog.get_logger(sync_policy.__name__))


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def _session(start: str, end: str, mode: str = "enabled") -> dict[str, str]:
    return {"trade_mode": mode, "week_start_time": start, "week_end_time": end}


def _policies() -> tuple[SyncPolicies, MagicMock, MagicMock]:
    fake_data, fake_quotes = MagicMock(), MagicMock()
    policies = SyncPolicies([binance_policy(data_provider=fake_data, quote_provider=fake_quotes)])
    return policies, fake_data, fake_quotes


def test_split_composite_normalizes_and_handles_missing_suffix() -> None:
    assert split_composite(" btcusdt:binance ") == ("BTCUSDT", "BINANCE")
    assert split_composite("BTCUSDT") == ("BTCUSDT", "")


def test_policy_for_resolves_by_suffix_only() -> None:
    policies, fake_data, _ = _policies()
    policy = policies.policy_for("btcusdt:binance")
    assert policy is not None
    assert policy.data_provider is fake_data
    assert policies.policy_for("BTCUSDT:OKX") is None
    assert policies.policy_for("nocolon") is None


def test_unknown_exchange_logs_once_per_exchange() -> None:
    policies, _, _ = _policies()
    with capture_logs() as logs:
        for _ in range(3):
            policies.policy_for("A:OKX")
        policies.policy_for("B:OKX")
    events = [e for e in logs if e["event"] == "market_data.unknown_exchange"]
    assert len(events) == 1
    assert events[0]["exchange"] == "OKX"


def test_binance_policy_values() -> None:
    policies, fake_data, fake_quotes = _policies()
    policy = policies.policy_for("BTCUSDT:BINANCE")
    assert policy is not None
    assert policy.exchange == "BINANCE"
    assert policy.data_provider is fake_data
    assert policy.quote_provider is fake_quotes
    assert policy.poll_intervals == (Interval.MINUTE_1,)
    assert policy.poll_n_bars == 100
    assert policy.cascade is True
    assert policy.cascade_lookback_minutes == 100
    assert policy.integrity_intervals == (
        Interval.MINUTE_1,
        Interval.MINUTE_5,
        Interval.MINUTE_15,
        Interval.HOUR_1,
        Interval.HOUR_4,
        Interval.DAY_1,
        Interval.WEEK_1,
    )
    assert policy.backfill_n_bars == 5000
    assert policy.poll_time_cap_s is None
    assert dict(policy.history_days) == {}
    assert dict(policy.calendars) == {}
    assert policies.quote_providers() == [fake_quotes]


def test_weekday_session_closes_over_the_weekend() -> None:
    calendar = MarketCalendar.from_week_sessions([_session("Mon, 00:00:00", "Fri, 23:59:59")])
    assert calendar.is_open(_at(FRI, 23, 59))
    assert not calendar.is_open(_at(SAT, 0, 0))
    assert not calendar.is_open(_at(SUN, 12, 0))
    assert calendar.is_open(_at(MON, 0, 0))


def test_daily_break_is_closed() -> None:
    calendar = MarketCalendar.from_week_sessions(
        [
            _session("Mon, 00:00:00", "Mon, 21:59:59"),
            _session("Mon, 23:00:00", "Tue, 21:59:59"),
        ]
    )
    assert not calendar.is_open(_at(MON, 22, 30))
    assert calendar.is_open(_at(MON, 23, 0))


def test_session_wrapping_the_week_boundary() -> None:
    calendar = MarketCalendar.from_week_sessions([_session("Sun, 22:00:00", "Mon, 01:00:00")])
    assert calendar.is_open(_at(SUN, 23, 0))
    assert calendar.is_open(_at(MON, 0, 30))


def test_disabled_session_is_ignored() -> None:
    calendar = MarketCalendar.from_week_sessions(
        [
            _session("Mon, 00:00:00", "Fri, 23:59:59"),
            _session("Sat, 00:00:00", "Sun, 23:59:59", mode="trading_disabled"),
        ]
    )
    assert not calendar.is_open(_at(SAT, 12, 0))


def test_naive_datetime_is_treated_as_utc() -> None:
    calendar = MarketCalendar.from_week_sessions([_session("Mon, 00:00:00", "Fri, 23:59:59")])
    assert calendar.is_open(datetime(2026, 10, FRI, 23, 59))
    assert not calendar.is_open(datetime(2026, 10, SAT, 0, 0))


def test_always_open_and_binance_calendar() -> None:
    policies, _, _ = _policies()
    assert ALWAYS_OPEN.is_open(_at(SAT, 12, 0))
    assert policies.market_calendar("BTCUSDT:BINANCE") is ALWAYS_OPEN
