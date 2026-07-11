"""Tests for the scoring engine — bands, weakest-axis, None re-normalization."""

from __future__ import annotations

from scripts.rubric.scoring import (
    RUBRIC_VERSION,
    THRESHOLDS,
    WEIGHTS,
    grade_from_score,
    score_axis,
    score_metric,
)


def test_rubric_version_is_string():
    assert isinstance(RUBRIC_VERSION, str)


def test_score_metric_higher_better_bands():
    assert score_metric("calmar", -0.5) == 0
    assert score_metric("calmar", 0.5) == 1
    assert score_metric("calmar", 2.5) == 3
    assert score_metric("calmar", 5.0) == 4


def test_score_metric_lower_better_ulcer():
    assert score_metric("ulcer_index", 1.0) == 4
    assert score_metric("ulcer_index", 3.0) == 3
    assert score_metric("ulcer_index", 20.0) == 0


def test_score_metric_range_optimal_mae_to_stop():
    assert score_metric("mae_to_stop", 0.3) == 1  # too wide
    assert score_metric("mae_to_stop", 0.7) == 4  # calibrated
    assert score_metric("mae_to_stop", 0.95) == 2  # too tight
    assert score_metric("mae_to_stop", 1.5) == 1


def test_score_metric_degrees_of_freedom():
    assert score_metric("degrees_of_freedom", 3) == 4
    assert score_metric("degrees_of_freedom", 5) == 3
    assert score_metric("degrees_of_freedom", 6) == 2
    assert score_metric("degrees_of_freedom", 12) == 0


def test_score_metric_none_and_unknown():
    assert score_metric("calmar", None) is None
    assert score_metric("not_a_metric", 1.0) is None


def test_grade_boundaries():
    assert grade_from_score(4.0) == "A"
    assert grade_from_score(3.5) == "A"
    assert grade_from_score(3.49) == "B"
    assert grade_from_score(1.5) == "C"
    assert grade_from_score(0.5) == "D"
    assert grade_from_score(0.0) == "F"


def test_weights_sum_to_one_per_axis():
    for axis, weights in WEIGHTS.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9, axis


def test_score_axis_none_renormalizes():
    # design_integrity with mfe_capture N/A: remaining three all top out at 4 → 4.0
    values = {
        "cost_to_edge": 2.0,
        "degrees_of_freedom": 3,
        "mfe_capture": None,
        "mae_to_stop": 0.7,
    }
    axis = score_axis("design_integrity", values)
    assert abs(axis.score - 4.0) < 1e-9
    dropped = [b for b in axis.breakdown if b["metric"] == "mfe_capture"][0]
    assert dropped["points"] is None


def test_weakest_axis_dominates():
    # performance A-grade inputs, robustness F-grade inputs
    perf = {
        "calmar": 5.0,
        "mar": 3.0,
        "ulcer_index": 1.0,
        "ulcer_performance_index": 3.0,
        "recovery_factor": 5.0,
    }
    rob = {
        "psr": 0.1,
        "sqn": 0.5,
        "tail_ratio": 0.5,
        "common_sense_ratio": 0.5,
        "gain_to_pain": -1.0,
    }
    pa = score_axis("performance", perf)
    ra = score_axis("robustness", rob)
    assert pa.grade == "A"
    assert ra.grade == "F"
    overall = min(pa.score, ra.score)
    assert grade_from_score(overall) in ("D", "F")


def test_thresholds_and_weights_share_metric_keys():
    # every weighted metric must have a threshold band (else it silently scores None)
    for axis, weights in WEIGHTS.items():
        for metric in weights:
            assert metric in THRESHOLDS, f"{axis}.{metric} missing threshold"
