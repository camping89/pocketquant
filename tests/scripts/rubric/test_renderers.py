"""Renderer tests — synthetic ScorecardResult, no DB. Cover md/html/json shape,
ranking, escaping, and caveat/version headers.
"""

from __future__ import annotations

import dataclasses
import json

from scripts.rubric.render_html import render_html
from scripts.rubric.render_markdown import (
    render_comparison_table,
    render_scorecard,
    render_scorecards_document,
)
from scripts.rubric.scoring import grade_from_score
from scripts.rubric.types import AxisScore, ScorecardResult


def _result(code: str, overall: float, diagnosis: str, aliases=None) -> ScorecardResult:
    axes = {
        "performance": AxisScore(
            "performance",
            overall,
            grade_from_score(overall),
            [
                {"metric": "calmar", "value": 1.2, "points": 2, "weight": 0.25},
                {"metric": "mar", "value": None, "points": None, "weight": 0.25},
            ],
        ),
        "robustness": AxisScore(
            "robustness", overall, "F",
            [{"metric": "psr", "value": 0.1, "points": 0, "weight": 0.3}],
        ),
        "design_integrity": AxisScore(
            "design_integrity", overall, "C",
            [{"metric": "cost_to_edge", "value": 0.78, "points": 1, "weight": 0.35}],
        ),
    }
    return ScorecardResult(
        run_id=f"run-{code}",
        strategy_code=code,
        symbol="BTCUSDT:BINANCE",
        interval="1m",
        name=None,
        rubric_version="1.0.0",
        axes=axes,
        overall_score=overall,
        overall_grade=grade_from_score(overall),
        metrics={"calmar": 1.2},
        reconciliation={
            "planned_rr_mean": 1.7,
            "planned_rr_median": 0.97,
            "realized_r_mean": -0.04,
            "realized_r_median": -1.0,
            "gross_edge_bps": 5.46,
            "friction_bps": 7.0,
            "net_edge_bps": -1.54,
        },
        excursions={
            "mfe_capture_mean": 0.81,
            "mae_to_stop_mean": 0.9,
            "mae_r_p50": -1.0,
            "mae_r_p90": -0.17,
            "mfe_r_p50": 0.96,
            "mfe_r_p90": 2.1,
            "low_coverage": False,
            "low_coverage_trades": 1,
            "total_trades": 8629,
        },
        audit={
            "degrees_of_freedom": 5,
            "params": ["a", "b"],
            "direction_bias": "both",
            "sl_tp_geometry": "geo",
            "entry_frequency_class": "stateful_setup",
            "lookahead_safety": "safe",
        },
        diagnosis=diagnosis,
        aliases=aliases or [],
    )


def _sample() -> list[ScorecardResult]:
    return [
        _result("hitnrun2", 0.30, "cost-killed", aliases=["alias-1"]),
        _result("engulfing", 0.15, "no directional edge"),
        _result("pullback", 1.20, "net-negative after costs"),
    ]


def test_comparison_table_ranks_weakest_first():
    md = render_comparison_table(_sample())
    assert md.index("engulfing") < md.index("hitnrun2")  # 0.15 before 0.30
    assert "RUBRIC_VERSION = 1.0.0" in md
    assert "Caveat" in md


def test_scorecard_shows_breakdown_and_aliases():
    r = _result("hitnrun2", 0.30, "cost-killed", aliases=["alias-1"])
    md = render_scorecard(r)
    assert "alias-1" in md
    assert "cost_to_edge" in md
    assert "Reconciliation" in md
    assert "Static audit" in md


def test_scorecards_document_has_all_runs():
    doc = render_scorecards_document(_sample())
    for code in ("hitnrun2", "engulfing", "pullback"):
        assert code in doc


def test_html_self_contained_and_escaped():
    html = render_html(_sample())
    assert html.startswith("<!doctype")
    assert html.rstrip().endswith("</html>")
    assert "Caveat" in html
    assert 'class="grade"' in html
    # dynamic text must be escaped
    bad = _result("x<script>", 0.1, "a & b < c")
    h2 = render_html([bad])
    assert "<script>" not in h2
    assert "&lt;script&gt;" in h2


def test_json_roundtrip_via_asdict():
    payload = {
        "rubric_version": "1.0.0",
        "runs": [dataclasses.asdict(r) for r in _sample()],
    }
    s = json.dumps(payload, default=str, indent=2)
    parsed = json.loads(s)
    assert len(parsed["runs"]) == 3
    assert parsed["runs"][0]["axes"]["performance"]["grade"] in "ABCDF"


def test_none_value_renders_as_dash():
    r = _result("engulfing", 0.15, "no directional edge")
    md = render_scorecard(r)
    # mar has value None in the breakdown → rendered as em-dash, not "None"
    assert "| mar | — |" in md
