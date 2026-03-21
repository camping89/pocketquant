"""Tests for domain value objects."""

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
        assert Interval.MONTH_1 == "1M"

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
