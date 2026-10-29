"""Annualization is the calendar's answer, not the clock's — and only for Sharpe.

An Exness FX year holds 312 daily bars (six a week: Sunday evening prints its
own), not 365 days. Sharpe and Sortino scale by the square root of that count,
so taking it from the wrong calendar silently misstates every risk-adjusted
figure a session-hours backtest reports.

CAGR is the opposite case and is pinned here too, because the obvious-looking
move — feeding the same session count into it — is wrong and costly.

The counts are asserted exactly rather than as a range. The adapter counts bar
opens over one fixed reference week precisely so a re-run reports the same
Sharpe. A range wide enough to be "safe" would accept 260 (Sunday's bar
dropped), 364 (the 24/7 week) and 6240 for gold (the daily break ignored), which
is everything worth catching.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.trading.performance_calculator_domain_service import (
    PerformanceCalculatorDomainService,
)
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import EXNESS_CALENDARS

FX, XAU, _CRYPTO = EXNESS_CALENDARS


def test_crypto_1m_is_525600() -> None:
    assert Continuous24x7Calendar().periods_per_year(Interval.MINUTE_1) == 525_600


def test_crypto_1d_is_365() -> None:
    assert Continuous24x7Calendar().periods_per_year(Interval.DAY_1) == 365


def test_exness_fx_daily_bars_per_year_is_the_reference_week_count() -> None:
    """312 = 6 daily bars a week x 52.

    EURUSD opens Sunday 21:05 UTC and closes Friday 20:58:59 UTC. Sunday's few
    evening hours still produce a daily bar and a daily return, so they count.
    """
    assert FX.periods_per_year(Interval.DAY_1) == 312.0


def test_exness_gold_hourly_is_the_reference_week_count() -> None:
    """5980 = 115 hourly bars a week x 52.

    Sunday 22:00 and 23:00 (2), Monday to Thursday 23 hours each (92), Friday
    00:00 to 20:00 (21). The only daily break is 20:58:00-22:00:29 UTC, which
    removes the 21:00 bar Monday to Thursday; the 22:00 bar stays because
    trading resumes at 22:00:30.
    """
    assert XAU.periods_per_year(Interval.HOUR_1) == 5_980.0


def test_cagr_stays_on_calendar_time_whatever_the_calendar() -> None:
    """A doubling over one calendar year is 100% CAGR on any instrument.

    Dividing wall-clock days by a 312-bar count would stretch that year to 1.17
    and report 81% instead. Sharpe takes the session count; CAGR must not.
    """
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    days = (end - start).days

    assert PerformanceCalculatorDomainService.cagr(10_000.0, 20_000.0, days) == 1.0
