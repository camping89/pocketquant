"""Pure-math tests for empirical metrics — no DB (import stays connection-free)."""

from __future__ import annotations

import numpy as np
import pytest

from scripts.rubric.empirical_metrics import (
    calmar,
    common_sense_ratio,
    cost_to_edge,
    gain_to_pain,
    kelly,
    mar,
    recovery_factor,
    risk_of_ruin,
    sqn,
    tail_ratio,
    ulcer_index,
    ulcer_performance_index,
)


def test_calmar_and_mar():
    assert calmar(0.30, -0.10) == pytest.approx(3.0)
    assert mar(0.20, -0.10) == pytest.approx(2.0)
    # zero drawdown → 0 (guard, not inf)
    assert calmar(0.30, 0.0) == 0.0
    assert mar(0.20, 0.0) == 0.0


def test_tail_ratio_symmetric_is_one():
    r = np.array([-3, -2, -1, 0, 1, 2, 3], dtype=float)
    assert abs(tail_ratio(r) - 1.0) < 1e-9


def test_tail_ratio_left_heavy_below_one():
    r = np.array([-10, -5, -1, 0, 1, 2, 3], dtype=float)
    assert tail_ratio(r) < 1.0


def test_ulcer_index_zero_when_no_drawdown():
    assert ulcer_index(np.zeros(10)) == 0.0
    assert ulcer_index(np.array([0.0])) == 0.0  # n<2


def test_ulcer_index_positive_with_drawdown():
    dd = np.array([0.0, -0.05, -0.10, -0.02])
    assert ulcer_index(dd) > 0.0


def test_ulcer_performance_index_guard():
    assert ulcer_performance_index(0.1, 0.0) == 0.0


def test_gain_to_pain():
    # gain_to_pain = Σ returns / |Σ negative returns|. Σ = 3, Σneg = -2 → 1.5
    r = np.array([2.0, -1.0, 3.0, -1.0])
    assert gain_to_pain(r) == pytest.approx(1.5)
    assert gain_to_pain(np.array([1.0, 2.0])) == 0.0  # no pain → 0 guard


def test_recovery_factor():
    assert recovery_factor(0.40, -0.10) == 4.0
    assert recovery_factor(0.40, 0.0) == 0.0


def test_kelly_positive_edge():
    # win_rate .6, win/loss ratio 2 → (2*.6 - .4)/2 = .4
    assert abs(kelly(0.6, 2.0) - 0.4) < 1e-9
    assert kelly(0.6, 0.0) == 0.0


def test_risk_of_ruin_bounds():
    assert risk_of_ruin(0.55, 5000) < 1e-6  # saturates to ~0
    assert risk_of_ruin(0.0, 100) == 1.0
    assert risk_of_ruin(1.0, 100) == 0.0
    assert risk_of_ruin(0.5, 0) == 1.0


def test_sqn_needs_two():
    assert sqn(np.array([1.0])) == 0.0
    # constant R → std 0 → guard 0
    assert sqn(np.array([1.0, 1.0, 1.0])) == 0.0
    r = np.array([1.0, -1.0, 2.0, -0.5, 1.5])
    assert isinstance(sqn(r), float)


def test_cost_to_edge_sign():
    assert cost_to_edge(7.0, 7.0) == 1.0
    assert cost_to_edge(-2.0, 7.0) < 0  # negative gross → negative ratio
    assert cost_to_edge(5.0, 0.0) == 0.0


def test_common_sense_ratio():
    assert common_sense_ratio(2.0, 1.5) == 3.0
