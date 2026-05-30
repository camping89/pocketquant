"""Unit tests for the backfill CLI arg parsing (offline, no API calls).

Kline→Bar mapping itself is exercised by the canonical mapper tests in
pocketquant-core (test_binance_client.py); this script imports that mapper.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pocketquant.core.domain.shared.enums import Interval

from scripts.backfill_1m_from_binance import (
    INTERVAL_TO_BINANCE,
    BackfillConfig,
    parse_args,
)


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
    """Every interval the backfill CLI accepts must map to a Binance literal."""
    required = {
        Interval.MINUTE_1,
        Interval.MINUTE_5,
        Interval.MINUTE_15,
        Interval.HOUR_1,
        Interval.HOUR_4,
        Interval.DAY_1,
    }
    assert required.issubset(INTERVAL_TO_BINANCE.keys())
