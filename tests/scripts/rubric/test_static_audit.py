from __future__ import annotations

import pytest

from scripts.rubric.static_audit import audit_strategy


def test_unknown_strategy_falls_back_not_raises():
    a = audit_strategy("does_not_exist")
    assert a["degrees_of_freedom"] is None
    assert a["direction_bias"] == "unknown"
    assert a["lookahead_safety"] == "unknown"
    assert "note" in a


@pytest.mark.usefixtures("probe_registry")
def test_degrees_of_freedom_count_the_declared_defaults():
    result = audit_strategy("probe")
    assert result["degrees_of_freedom"] == 1
    assert result["params"] == ["min_bars"]
