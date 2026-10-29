from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pocketquant.core.domain.bar.services.bar_builder_domain_service import (
    get_bar_start,
    is_bar_aligned,
)
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import (
    _BTCUSD_SESSIONS,
    _EURUSD_SESSIONS,
    _XAUUSD_SESSIONS,
    EXNESS_CALENDARS,
)
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.engine.market_data.app_services.sync_jobs import SYNC_INTERVALS

FIXTURES = Path(__file__).parents[1] / "exness" / "fixtures"
FX, XAU, CRYPTO = EXNESS_CALENDARS


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_the_session_tables_are_the_recorded_ones() -> None:
    assert _EURUSD_SESSIONS == _load("conditions_EURUSD.json")["trade_sessions"]
    assert _XAUUSD_SESSIONS == _load("conditions_XAUUSD.json")["trade_sessions"]
    assert _BTCUSD_SESSIONS == _load("conditions_BTCUSD.json")["trade_sessions"]


@pytest.mark.parametrize(
    ("instant", "is_open"),
    [
        ("2026-10-13T09:28:00", True),
        ("2026-10-13T20:58:00", False),
        ("2026-10-13T21:30:00", False),
        ("2026-10-13T22:00:30", True),
        ("2026-10-17T12:00:00", False),
        ("2026-10-18T22:01:30", True),
        ("2026-10-16T20:57:59", True),
        ("2026-10-16T20:58:00", False),
    ],
)
def test_xauusd_hours(instant: str, is_open: bool) -> None:
    assert XAU.is_open(_at(instant)) is is_open


@pytest.mark.parametrize(
    ("instant", "is_open"),
    [
        # Last week under EDT: the recorded UTC hours.
        ("2026-10-27T20:57:59", True),
        ("2026-10-27T20:58:00", False),
        ("2026-10-27T22:00:30", True),
        ("2026-10-30T20:58:00", False),
        # US daylight saving ends on 2026-11-01: one hour later in UTC.
        ("2026-11-01T22:01:30", False),
        ("2026-11-01T23:01:30", True),
        ("2026-11-03T20:58:00", True),
        ("2026-11-03T21:57:59", True),
        ("2026-11-03T21:58:00", False),
        ("2026-11-03T22:00:30", False),
        ("2026-11-03T23:00:30", True),
        ("2026-11-06T21:57:59", True),
        ("2026-11-06T21:58:00", False),
    ],
)
def test_xauusd_hours_follow_new_york_across_the_dst_change(instant: str, is_open: bool) -> None:
    assert XAU.is_open(_at(instant)) is is_open


@pytest.mark.parametrize(
    ("instant", "is_open"),
    [
        ("2026-10-13T21:30:00", True),
        ("2026-10-16T20:58:59", True),
        ("2026-10-16T20:59:00", False),
        ("2026-10-18T21:05:00", True),
        ("2026-10-18T21:04:59", False),
    ],
)
def test_eurusd_hours(instant: str, is_open: bool) -> None:
    assert FX.is_open(_at(instant)) is is_open


@pytest.mark.parametrize(
    ("instant", "is_open"),
    [
        ("2026-10-30T20:58:59", True),
        ("2026-10-30T20:59:00", False),
        ("2026-11-01T21:05:00", False),
        ("2026-11-01T22:05:00", True),
        ("2026-11-06T21:58:59", True),
        ("2026-11-06T21:59:00", False),
    ],
)
def test_eurusd_hours_follow_new_york_across_the_dst_change(instant: str, is_open: bool) -> None:
    assert FX.is_open(_at(instant)) is is_open


def test_the_dst_change_moves_the_session_edges_in_utc() -> None:
    before = XAU.trading_minutes(_at("2026-10-27T20:00:00"), _at("2026-10-27T23:00:00"))
    after = XAU.trading_minutes(_at("2026-11-03T20:00:00"), _at("2026-11-03T23:00:00"))

    assert before[57:59] == [_at("2026-10-27T20:57:00"), _at("2026-10-27T22:00:00")]
    assert _at("2026-11-03T21:57:00") in after
    assert _at("2026-11-03T21:58:00") not in after
    assert _at("2026-11-03T22:30:00") not in after
    assert XAU.session_close(date(2026, 11, 6)) == _at("2026-11-06T21:57:59")


def test_crypto_trades_through_the_week_and_the_dst_change() -> None:
    start, end = _at("2026-10-29T00:00:00"), _at("2026-11-04T00:00:00")

    assert len(CRYPTO.trading_minutes(start, end)) == (end - start) // timedelta(minutes=1)
    assert CRYPTO.is_open(_at("2026-11-01T06:30:00"))
    assert CRYPTO.sessions(start, end - timedelta(seconds=1)) == [
        date(2026, 10, 29) + timedelta(days=i) for i in range(6)
    ]


@pytest.mark.parametrize(
    ("calendar", "fixture"),
    [(XAU, "candles_XAUUSD_M1.json"), (FX, "candles_EURUSD_M1.json")],
)
def test_every_recorded_bar_is_a_trading_minute(calendar: Any, fixture: str) -> None:
    times = [datetime.fromisoformat(c["time"]) for c in _load(fixture)["candles"]]

    minutes = set(calendar.trading_minutes(times[0], times[-1] + timedelta(minutes=1)))

    assert set(times) <= minutes


def test_the_daily_grid_matches_the_recorded_d1_candles() -> None:
    recorded = {
        datetime.fromisoformat(c["time"]) for c in _load("candles_XAUUSD_D1.json")["candles"]
    }

    expected = {
        XAU.session_open(d)
        for d in XAU.sessions(_at("2026-10-02T00:00:00"), _at("2026-10-13T00:00:00"))
    }

    assert expected == recorded


def test_sunday_before_the_open_is_not_yet_a_session() -> None:
    sunday = _at("2026-10-18T00:00:00")

    assert XAU.sessions(sunday, sunday) == []
    with pytest.raises(KeyError):
        XAU.session_open(date(2026, 10, 17))


def test_bar_start_is_the_utc_grid_with_sunday_weeks() -> None:
    instant = _at("2026-10-13T09:28:37")

    for calendar in EXNESS_CALENDARS:
        for interval in SYNC_INTERVALS:
            expected = (
                _at("2026-10-11T00:00:00")
                if interval == Interval.WEEK_1
                else get_bar_start(instant, interval)
            )
            assert calendar.bar_start(instant, interval) == expected


@pytest.mark.parametrize(
    ("instant", "week"),
    [
        ("2026-10-18T00:00:00", "2026-10-18T00:00:00"),
        ("2026-10-17T23:59:59", "2026-10-11T00:00:00"),
        ("2026-10-19T08:00:00", "2026-10-18T00:00:00"),
    ],
)
def test_a_week_opens_on_sunday_midnight(instant: str, week: str) -> None:
    assert XAU.bar_start(_at(instant), Interval.WEEK_1) == _at(week)


def test_the_weekly_bars_prod_returned_are_aligned() -> None:
    sunday, monday = _at("2026-10-11T00:00:00"), _at("2026-10-12T00:00:00")

    for calendar in EXNESS_CALENDARS:
        assert is_bar_aligned(sunday, Interval.WEEK_1, calendar)
        assert not is_bar_aligned(monday, Interval.WEEK_1, calendar)


def test_previous_close_and_session_close() -> None:
    assert XAU.previous_close(_at("2026-10-17T12:00:00")) == _at("2026-10-16T20:57:59")
    assert XAU.previous_close(_at("2026-10-13T09:28:00")) == _at("2026-10-13T09:28:00")
    assert XAU.session_close(date(2026, 10, 16)) == _at("2026-10-16T20:57:59")
    assert FX.session_close(date(2026, 10, 13)) == _at("2026-10-13T23:59:59")


@pytest.mark.parametrize(
    ("instant", "is_open"),
    [
        # US daylight saving starts on 2027-03-14: back to the recorded UTC hours.
        ("2027-03-12T21:57:59", True),
        ("2027-03-12T21:58:00", False),
        ("2027-03-14T22:01:30", True),
        ("2027-03-16T20:58:00", False),
        ("2027-03-16T22:00:30", True),
    ],
)
def test_xauusd_hours_follow_new_york_into_daylight_saving(instant: str, is_open: bool) -> None:
    assert XAU.is_open(_at(instant)) is is_open


@pytest.mark.parametrize(
    ("calendar", "daily", "weekly"),
    [(FX, 312, 52), (XAU, 312, 52), (CRYPTO, 364, 52)],
)
def test_periods_per_year_counts_bars(calendar: Any, daily: int, weekly: int) -> None:
    assert calendar.periods_per_year(Interval.DAY_1) == daily
    assert calendar.periods_per_year(Interval.WEEK_1) == weekly
    assert CRYPTO.periods_per_year(Interval.HOUR_1) == 24 * 7 * 52


def test_the_factory_resolves_every_exness_calendar() -> None:
    factory = TradingCalendarFactory(MagicMock())

    for calendar_id in ("EXNESS_FX", "EXNESS_XAUUSD", "EXNESS_CRYPTO"):
        assert factory.get(calendar_id).calendar_id == calendar_id
