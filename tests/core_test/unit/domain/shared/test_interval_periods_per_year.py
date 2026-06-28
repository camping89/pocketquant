"""Interval.periods_per_year — bars/year used to annualize Sharpe/Sortino."""

from __future__ import annotations

import pytest

from pocketquant.core.domain.shared.enums import Interval


@pytest.mark.parametrize(
    ("interval", "expected"),
    [
        (Interval.MINUTE_1, 525600),
        (Interval.MINUTE_5, 105120),
        (Interval.MINUTE_15, 35040),
        (Interval.HOUR_1, 8760),
        (Interval.HOUR_4, 2190),
        (Interval.DAY_1, 365),
    ],
)
def test_periods_per_year_for_each_interval(interval: Interval, expected: float) -> None:
    assert interval.periods_per_year == expected


def test_weekly_is_365_over_7() -> None:
    assert Interval.WEEK_1.periods_per_year == pytest.approx(365 / 7)


def test_safe_lookup_known_interval_matches_property() -> None:
    assert Interval.periods_per_year_for("1m") == Interval.MINUTE_1.periods_per_year


def test_safe_lookup_unknown_interval_returns_none_not_raises() -> None:
    # A stale/queued request may carry an interval no longer in the enum;
    # annualization must skip rather than raise.
    assert Interval.periods_per_year_for("3m") is None
    assert Interval.periods_per_year_for("") is None
