"""Annualization is the calendar's answer, not the clock's — and only for Sharpe.

A CME Globex equity year holds 259 sessions of up to 23 hours less a daily
15-minute halt, not 365 days of
24. Sharpe and Sortino scale by the square root of that count, so taking it from
the wrong calendar silently misstates every risk-adjusted figure a futures
backtest reports.

CAGR is the opposite case and is pinned here too, because the obvious-looking
move — feeding the same session count into it — is wrong and costly.

The counts are asserted exactly rather than as a range. The adapter measures
them over a fixed 2025 reference window precisely so a re-run reports the same
Sharpe, and 2025 is a closed year whose holiday set can no longer change. A
range wide enough to be "safe" would accept 261 (holiday filter dropped), 260
(window drifted to 2024) and 252 (an equity-cash basis), which is everything
worth catching.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.trading.performance_calculator_domain_service import (
    PerformanceCalculatorDomainService,
)
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter


def test_crypto_1m_is_525600() -> None:
    assert Continuous24x7Calendar().periods_per_year(Interval.MINUTE_1) == 525_600


def test_crypto_1d_is_365() -> None:
    assert Continuous24x7Calendar().periods_per_year(Interval.DAY_1) == 365


def test_cme_sessions_per_year_is_the_2025_reference_count() -> None:
    """259 = 261 weekdays in 2025, less the two full closures (Jan 1, Dec 25).

    CME Globex equity futures do not skip US holidays; they close early. Those
    sessions still produce a daily bar and a daily return, so they count.
    """
    assert CmeGlobexCalendarAdapter().periods_per_year(Interval.DAY_1) == 259.0


def test_cme_hourly_is_the_2025_reference_count() -> None:
    """5848 = 259 sessions x 23h, less early closes and the daily 15-minute halt.

    Equity-index futures pause 15:15-15:30 Chicago, just after the cash equity
    close, on top of the 16:00-17:00 maintenance break. It was 5910 before that
    halt was modelled; the 62-hour difference is not a clean 259 x 15 minutes
    because an early close can land before the halt, leaving that session with
    a shortened one or none at all.
    """
    assert CmeGlobexCalendarAdapter().periods_per_year(Interval.HOUR_1) == 5_848.0


def test_cagr_stays_on_calendar_time_whatever_the_calendar() -> None:
    """A doubling over one calendar year is 100% CAGR on any instrument.

    Dividing wall-clock days by a session count would stretch that year to 1.41
    and report 63.5% instead. Sharpe takes the session count; CAGR must not.
    """
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    days = (end - start).days

    assert PerformanceCalculatorDomainService.cagr(10_000.0, 20_000.0, days) == 1.0
