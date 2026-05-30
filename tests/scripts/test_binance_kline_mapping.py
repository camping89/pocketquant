"""Unit tests for Binance kline -> Bar mapping (offline, no API calls)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pocketquant.core.domain.shared.enums import Interval

from scripts.backfill_1m_from_binance import (
    INTERVAL_TO_BINANCE,
    BackfillConfig,
    kline_to_bar,
    parse_args,
)

# Sample kline from Binance docs (positional schema):
#   [open_time_ms, open, high, low, close, volume, close_time_ms,
#    quote_volume, trades, taker_buy_base, taker_buy_quote, ignore]
SAMPLE_KLINE_1M = [
    1714465200000,  # 2024-04-30T08:20:00Z (minute aligned)
    "60000.10",
    "60100.55",
    "59950.00",
    "60050.25",
    "12.34567890",
    1714465259999,
    "740123.45",
    87,
    "5.12000000",
    "300000.00",
    "0",
]


def test_kline_to_bar_basic() -> None:
    bar = kline_to_bar(SAMPLE_KLINE_1M, "btcusdt", "binance", Interval.MINUTE_1)

    assert bar.symbol == "BTCUSDT:BINANCE"
    assert bar.interval == Interval.MINUTE_1
    assert bar.datetime == datetime(2024, 4, 30, 8, 20, 0, tzinfo=UTC)
    assert bar.open == pytest.approx(60000.10)
    assert bar.high == pytest.approx(60100.55)
    assert bar.low == pytest.approx(59950.00)
    assert bar.close == pytest.approx(60050.25)
    assert bar.volume == pytest.approx(12.34567890)
    assert bar.tick_count == 87


def test_open_time_minute_aligned() -> None:
    bar = kline_to_bar(SAMPLE_KLINE_1M, "BTCUSDT", "BINANCE", Interval.MINUTE_1)
    assert bar.datetime is not None
    assert bar.datetime.second == 0
    assert bar.datetime.microsecond == 0
    # ms epoch must be exactly minute-aligned
    assert int(bar.datetime.timestamp() * 1000) % 60_000 == 0


def test_volume_and_trades_parsed_as_numbers() -> None:
    """Strings from Binance must coerce to float (volume) and int (trades)."""
    bar = kline_to_bar(SAMPLE_KLINE_1M, "BTCUSDT", "BINANCE", Interval.MINUTE_1)
    assert isinstance(bar.volume, float)
    assert isinstance(bar.tick_count, int)
    assert isinstance(bar.open, float)
    assert isinstance(bar.high, float)
    assert isinstance(bar.low, float)
    assert isinstance(bar.close, float)


def test_unknown_interval_rejected_by_cli() -> None:
    """parse_args should reject intervals not in INTERVAL_TO_BINANCE."""
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--symbol",
                "BTCUSDT",
                "--interval",
                "7m",  # not a valid Interval
                "--start",
                "2026-04-30T00:00:00Z",
                "--end",
                "2026-04-30T01:00:00Z",
            ]
        )


def test_parse_args_valid() -> None:
    cfg = parse_args(
        [
            "--symbol",
            "btcusdt",
            "--exchange",
            "binance",
            "--start",
            "2026-04-30T08:54:00Z",
            "--end",
            "2026-05-03T21:34:00Z",
            "--dry-run",
        ]
    )
    assert isinstance(cfg, BackfillConfig)
    assert cfg.symbol == "BTCUSDT"
    assert cfg.exchange == "BINANCE"
    assert cfg.interval == Interval.MINUTE_1
    assert cfg.dry_run is True
    assert cfg.start == datetime(2026, 4, 30, 8, 54, 0, tzinfo=UTC)
    assert cfg.end == datetime(2026, 5, 3, 21, 34, 0, tzinfo=UTC)


def test_parse_args_rejects_inverted_range() -> None:
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--symbol",
                "BTCUSDT",
                "--start",
                "2026-05-03T21:34:00Z",
                "--end",
                "2026-04-30T08:54:00Z",
            ]
        )


def test_interval_map_covers_target_intervals() -> None:
    """The intervals listed in plan F2 must all map to a Binance literal."""
    required = {
        Interval.MINUTE_1,
        Interval.MINUTE_5,
        Interval.MINUTE_15,
        Interval.HOUR_1,
        Interval.HOUR_4,
        Interval.DAY_1,
    }
    assert required.issubset(INTERVAL_TO_BINANCE.keys())
