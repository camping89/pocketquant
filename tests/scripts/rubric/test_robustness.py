"""Pure-math tests for robustness — PSR (erf CDF) + sequencing bootstrap."""

from __future__ import annotations

import numpy as np

from scripts.rubric.robustness import (
    bootstrap_max_drawdown,
    kurtosis,
    normal_cdf,
    psr,
    skewness,
)


def test_normal_cdf_reference_points():
    assert abs(normal_cdf(0.0) - 0.5) < 1e-9
    assert abs(normal_cdf(1.96) - 0.975) < 1e-3
    assert abs(normal_cdf(-1.96) - 0.025) < 1e-3


def test_psr_high_sharpe_large_n_confident():
    # positive Sharpe, symmetric, large n → PSR near 1
    assert psr(1.0, 0.0, 3.0, 1000) > 0.99


def test_psr_negative_sharpe_low():
    assert psr(-1.0, 0.0, 3.0, 1000) < 0.01


def test_psr_bounds_and_small_n():
    assert psr(0.5, 0.0, 3.0, 1) == 0.0  # n<2
    assert 0.0 <= psr(0.5, 1.0, 5.0, 100) <= 1.0


def test_psr_denominator_guard():
    # very high sharpe + low kurtosis can drive the variance term non-positive;
    # must not raise, resolves by numerator sign.
    assert psr(50.0, 0.0, 0.0, 100) in (0.0, 1.0)


def test_kurtosis_normal_is_three():
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(50_000)
    assert abs(kurtosis(sample) - 3.0) < 0.15


def test_skewness_symmetric_near_zero():
    r = np.array([-3, -2, -1, 0, 1, 2, 3], dtype=float)
    assert abs(skewness(r)) < 1e-9


def test_bootstrap_seeded_reproducible():
    pnls = np.array([1.0, -1.0, 2.0, -0.5, 1.5, -2.0, 0.5])
    a = bootstrap_max_drawdown(pnls, 100.0, n_iter=200, seed=7)
    b = bootstrap_max_drawdown(pnls, 100.0, n_iter=200, seed=7)
    assert a["p95"] == b["p95"]
    assert a["p50"] == b["p50"]


def test_bootstrap_losses_first_worse_than_p95():
    # front-loaded losses → observed order is worse (more negative) than most
    # random reorderings → observed < p95.
    pnls = np.array([-1.0] * 10 + [1.0] * 12, dtype=float)
    out = bootstrap_max_drawdown(pnls, 100.0, n_iter=2000, seed=1)
    assert out["observed_maxdd"] < out["p95"]


def test_bootstrap_empty_or_degenerate():
    assert bootstrap_max_drawdown(np.array([1.0]), 100.0)["p95"] == 0.0
    assert bootstrap_max_drawdown(np.array([1.0, 2.0]), 0.0)["p95"] == 0.0
