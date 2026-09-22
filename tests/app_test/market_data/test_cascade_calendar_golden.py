"""Golden snapshot of crypto bucket, alignment and annualization arithmetic.

Captured against the pre-calendar implementation. Threading a trading calendar
through the pipeline must reproduce these values exactly for the 24/7 calendar;
any drift here is crypto bars silently moving, which is the one outcome the
calendar refactor is not allowed to have.

Regenerate deliberately and never as a reaction to a failure::

    POCKETQUANT_REGEN_GOLDEN=1 uv run pytest \
        tests/app_test/market_data/test_cascade_calendar_golden.py

A failing comparison means the production code changed, not that the snapshot
is stale.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from pocketquant.core.domain.bar.services.bar_builder_domain_service import get_bar_start
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.app_services.cascade_aggregator import (
    CASCADE_TFS,
    compute_boundaries,
)

GOLDEN_DIR = Path(__file__).parent / "golden"
_REGEN = os.environ.get("POCKETQUANT_REGEN_GOLDEN") == "1"

# A two-day window, long enough that every cascade timeframe produces more than
# one bucket and the 1d bucket boundary is exercised.
RANGE_START = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
RANGE_END = datetime(2026, 6, 3, 0, 0, tzinfo=UTC)

# Twelve instants around both 2026 US DST transitions (spring forward March 8,
# fall back November 1), plus ordinary mid-year instants. Deliberately not
# aligned to any interval, so each one exercises the flooring path.
SAMPLE_INSTANTS = [
    datetime(2026, 3, 7, 23, 30, 0, tzinfo=UTC),
    datetime(2026, 3, 8, 0, 0, 0, tzinfo=UTC),
    datetime(2026, 3, 8, 7, 59, 0, tzinfo=UTC),
    datetime(2026, 3, 8, 8, 0, 0, tzinfo=UTC),
    datetime(2026, 3, 8, 12, 34, 56, tzinfo=UTC),
    datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC),
    datetime(2026, 6, 15, 13, 45, 0, tzinfo=UTC),
    datetime(2026, 10, 31, 22, 15, 0, tzinfo=UTC),
    datetime(2026, 11, 1, 6, 59, 0, tzinfo=UTC),
    datetime(2026, 11, 1, 7, 0, 0, tzinfo=UTC),
    datetime(2026, 11, 1, 8, 0, 0, tzinfo=UTC),
    datetime(2026, 11, 3, 17, 7, 13, tzinfo=UTC),
]


def _compare(name: str, actual: dict) -> None:
    path = GOLDEN_DIR / name
    if _REGEN:
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        return
    expected = json.loads(path.read_text())
    assert actual == expected, f"{name} drifted from the captured crypto behaviour"


def _cascade_boundaries() -> dict:
    return {
        tf.value: [b.isoformat() for b in compute_boundaries(tf, RANGE_START, RANGE_END)]
        for tf in CASCADE_TFS
    }


def _aligned_bars() -> dict:
    return {
        interval.value: {
            sample.isoformat(): get_bar_start(sample, interval).isoformat()
            for sample in SAMPLE_INSTANTS
        }
        for interval in Interval
    }


def _periods_per_year() -> dict:
    return {interval.value: interval.periods_per_year for interval in Interval}


def test_cascade_boundaries_match_golden() -> None:
    _compare("cascade_boundaries.json", _cascade_boundaries())


def test_aligned_bars_match_golden() -> None:
    _compare("aligned_bars.json", _aligned_bars())


def test_periods_per_year_match_golden() -> None:
    _compare("periods_per_year.json", _periods_per_year())
