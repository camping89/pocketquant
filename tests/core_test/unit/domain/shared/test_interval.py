"""Interval enum — value objects, INTERVAL_SECONDS mapping, periods_per_year annualization."""

from __future__ import annotations

import pytest

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS


class TestInterval:
    """Tests for Interval enum."""

    def test_interval_values(self):
        """Test Interval enum has expected values."""
        assert Interval.MINUTE_1 == "1m"
        assert Interval.HOUR_1 == "1h"
        assert Interval.DAY_1 == "1d"
        assert Interval.WEEK_1 == "1w"

    def test_interval_seconds_mapping(self):
        """Test INTERVAL_SECONDS mapping is complete."""
        assert INTERVAL_SECONDS[Interval.MINUTE_1] == 60
        assert INTERVAL_SECONDS[Interval.MINUTE_5] == 300
        assert INTERVAL_SECONDS[Interval.HOUR_1] == 3600
        assert INTERVAL_SECONDS[Interval.DAY_1] == 86400
        assert INTERVAL_SECONDS[Interval.WEEK_1] == 604800

    def test_all_intervals_have_seconds(self):
        """Test all Interval values have corresponding seconds."""
        for interval in Interval:
            assert interval in INTERVAL_SECONDS, f"{interval} missing from INTERVAL_SECONDS"


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
