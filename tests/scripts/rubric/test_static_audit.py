"""AST audit tests — run on the 3 real strategies. Imports STRATEGY_REGISTRY to
resolve source files; strategies are parsed, never instantiated or run (no DB).
"""

from __future__ import annotations

import pytest

from scripts.rubric.static_audit import audit_strategy

_STRATEGIES = ["engulfing", "engulfing_pullback30_touch", "hitnrun2"]


@pytest.mark.parametrize("code", _STRATEGIES)
def test_audit_does_not_crash(code):
    a = audit_strategy(code)
    assert a["strategy_code"] == code
    assert a["degrees_of_freedom"] is not None


def test_degrees_of_freedom_match_defaults():
    # DoF = number of tunable params in each strategy's _DEFAULTS.
    assert audit_strategy("engulfing")["degrees_of_freedom"] == 4
    assert audit_strategy("engulfing_pullback30_touch")["degrees_of_freedom"] == 5
    assert audit_strategy("hitnrun2")["degrees_of_freedom"] == 6


@pytest.mark.parametrize("code", _STRATEGIES)
def test_direction_bias_both(code):
    assert audit_strategy(code)["direction_bias"] == "both"


@pytest.mark.parametrize("code", _STRATEGIES)
def test_lookahead_safe(code):
    # all three use the prev_bar + snapshot-before-append pattern
    assert audit_strategy(code)["lookahead_safety"] == "safe"


def test_geometry_recognized_for_engulfing():
    a = audit_strategy("engulfing_pullback30_touch")
    assert "pattern_extreme" in a["sl_tp_geometry"]


def test_unknown_strategy_falls_back_not_raises():
    a = audit_strategy("does_not_exist")
    assert a["degrees_of_freedom"] is None
    assert a["direction_bias"] == "unknown"
    assert a["lookahead_safety"] == "unknown"
    assert "note" in a
