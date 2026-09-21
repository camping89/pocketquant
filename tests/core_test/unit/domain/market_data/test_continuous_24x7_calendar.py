"""The 24/7 calendar must reproduce today's crypto behaviour exactly.

Phase 3 threads a calendar through sync, cascade, integrity and annualization.
If any method here disagrees with what the crypto path does today, that refactor
silently changes live bar values — so each test pins the method to the existing
implementation rather than to a hand-written expectation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pocketquant.core.domain.bar.services.bar_builder_domain_service import get_bar_start
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval

CALENDAR = Continuous24x7Calendar()


@pytest.mark.parametrize(
    "instant",
    [
        datetime(2026, 6, 6, 12, 0, tzinfo=UTC),  # Saturday
        datetime(2026, 12, 25, 0, 0, tzinfo=UTC),  # Christmas
        datetime(2026, 3, 8, 7, 30, tzinfo=UTC),  # US spring-forward
    ],
)
def test_is_open_always_true(instant: datetime) -> None:
    assert CALENDAR.is_open(instant) is True


def test_session_date_is_utc_date() -> None:
    # 23:30 in Chicago is already the next UTC day; crypto keys on UTC.
    instant = datetime(2026, 6, 11, 4, 30, tzinfo=UTC)

    assert CALENDAR.session_date(instant) == date(2026, 6, 11)


@pytest.mark.parametrize("interval", list(Interval))
def test_bar_start_matches_get_bar_start(interval: Interval) -> None:
    instant = datetime(2026, 6, 3, 14, 37, 13, tzinfo=UTC)

    assert CALENDAR.bar_start(instant, interval) == get_bar_start(instant, interval)


def test_previous_close_is_identity() -> None:
    instant = datetime(2026, 6, 3, 14, 37, tzinfo=UTC)

    assert CALENDAR.previous_close(instant) == instant


def test_trading_minutes_is_dense() -> None:
    start = datetime(2026, 6, 3, 0, 0, tzinfo=UTC)
    end = start + timedelta(hours=2)

    minutes = CALENDAR.trading_minutes(start, end)

    assert len(minutes) == 120
    assert minutes[0] == start
    assert minutes[-1] == end - timedelta(minutes=1)


@pytest.mark.parametrize("interval", list(Interval))
def test_periods_per_year_matches_interval_enum(interval: Interval) -> None:
    assert CALENDAR.periods_per_year(interval) == interval.periods_per_year
