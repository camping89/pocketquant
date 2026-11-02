from datetime import UTC, datetime

import pytest

from pocketquant.core.domain.strategy import Direction, Signal


def _signal(**overrides) -> Signal:
    fields = {
        "symbol": "BTCUSDT:BINANCE",
        "direction": Direction.LONG,
        "confidence": 1.0,
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "subscription_id": "s1",
    }
    return Signal(**(fields | overrides))


def test_a_stop_entry_needs_an_entry_price() -> None:
    with pytest.raises(ValueError):
        _signal(entry_type="stop")


def test_a_stop_entry_needs_a_long_or_short_side() -> None:
    with pytest.raises(ValueError):
        _signal(direction=Direction.EXIT, entry_type="stop", entry_price=101.0)


def test_a_market_signal_defaults_to_market() -> None:
    assert _signal().entry_type == "market"
