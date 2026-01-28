"""Tests for domain value objects."""

import pytest

from src.domain.shared.value_objects import INTERVAL_SECONDS, Interval, Symbol


class TestSymbol:
    """Tests for Symbol value object."""

    def test_symbol_creation(self):
        """Test creating a valid Symbol."""
        symbol = Symbol(code="AAPL", exchange="NASDAQ")
        assert symbol.code == "AAPL"
        assert symbol.exchange == "NASDAQ"

    def test_symbol_requires_code(self):
        """Test Symbol requires non-empty code."""
        with pytest.raises(ValueError, match="Symbol code is required"):
            Symbol(code="", exchange="NASDAQ")

    def test_symbol_requires_exchange(self):
        """Test Symbol requires non-empty exchange."""
        with pytest.raises(ValueError, match="Exchange is required"):
            Symbol(code="AAPL", exchange="")

    def test_symbol_string_representation(self):
        """Test Symbol string format."""
        symbol = Symbol(code="AAPL", exchange="NASDAQ")
        assert str(symbol) == "NASDAQ:AAPL"

    def test_symbol_from_string(self):
        """Test parsing Symbol from string format."""
        symbol = Symbol.from_string("NASDAQ:AAPL")
        assert symbol.code == "AAPL"
        assert symbol.exchange == "NASDAQ"

    def test_symbol_from_string_uppercase(self):
        """Test parsing normalizes to uppercase."""
        symbol = Symbol.from_string("nasdaq:aapl")
        assert symbol.code == "AAPL"
        assert symbol.exchange == "NASDAQ"

    def test_symbol_from_string_invalid(self):
        """Test parsing invalid format raises error."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol.from_string("INVALID")

    def test_symbol_is_immutable(self):
        """Test Symbol is frozen (immutable)."""
        symbol = Symbol(code="AAPL", exchange="NASDAQ")
        with pytest.raises(Exception):  # dataclass frozen raises FrozenInstanceError
            symbol.code = "GOOGL"  # type: ignore


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
