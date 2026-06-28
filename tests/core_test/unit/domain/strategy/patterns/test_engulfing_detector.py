"""Golden-fixture parity test for detect_engulfing.

The same fixture drives the TS chart port (Phase 3 vitest), so this file is the
Python half of the cross-runtime lock on the engulfing definition.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pocketquant.core.domain.strategy.patterns import detect_engulfing

_FIXTURE = Path(__file__).parent / "engulfing_golden_fixture.json"


def _load_cases() -> list[dict]:
    data = json.loads(_FIXTURE.read_text())
    return data["cases"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_detect_engulfing_matches_golden_fixture(case: dict) -> None:
    result = detect_engulfing(case["prev"], case["curr"])
    expected = case["expected"]

    assert result.is_bullish == expected["is_bullish"]
    assert result.is_bearish == expected["is_bearish"]
    assert result.rejection_wick_pct == pytest.approx(expected["rejection_wick_pct"])


def test_rejection_wick_pct_is_always_float() -> None:
    for case in _load_cases():
        result = detect_engulfing(case["prev"], case["curr"])
        assert isinstance(result.rejection_wick_pct, float)
