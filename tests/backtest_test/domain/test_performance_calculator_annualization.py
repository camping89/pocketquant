"""PerformanceCalculatorDomainService Sharpe/Sortino — per-interval annualization.

Pins the keyword-only ``periods_per_year`` contract and known-curve → known-value
math, and that cagr stays calendar-based (unaffected by the interval change).
"""

from __future__ import annotations

import inspect
import warnings

import numpy as np
import pytest

from pocketquant.backtest.domain.services.performance_calculator_domain_service import (
    PerformanceCalculatorDomainService,
)
from pocketquant.core.domain.shared.enums import Interval


def test_periods_per_year_is_keyword_only() -> None:
    # Guards against a positional collision with risk_free_rate.
    sig = inspect.signature(PerformanceCalculatorDomainService.sharpe_ratio)
    assert sig.parameters["periods_per_year"].kind is inspect.Parameter.KEYWORD_ONLY
    sig_s = inspect.signature(PerformanceCalculatorDomainService.sortino_ratio)
    assert sig_s.parameters["periods_per_year"].kind is inspect.Parameter.KEYWORD_ONLY


def test_sharpe_zero_variance_returns_zero() -> None:
    # Exactly-constant returns → sample std 0 → guard returns 0.0.
    flat = np.array([100.0, 100.0, 100.0, 100.0])
    assert PerformanceCalculatorDomainService.sharpe_ratio(flat, periods_per_year=365) == 0.0


def test_sharpe_known_curve_known_value() -> None:
    # Alternating returns +1% / -1% (approx): mean ~0 → Sharpe near 0.
    equity = np.array([100.0, 101.0, 100.0, 101.0, 100.0, 101.0])
    returns = np.diff(equity) / equity[:-1]
    mean, std = returns.mean(), returns.std(ddof=1)
    expected = (mean * 365) / (std * np.sqrt(365))
    assert PerformanceCalculatorDomainService.sharpe_ratio(
        equity, periods_per_year=365
    ) == pytest.approx(expected)


def test_sharpe_scales_with_sqrt_periods_per_year() -> None:
    rng = np.random.default_rng(7)
    returns = rng.normal(0.001, 0.01, 2000)
    equity = 100.0 * np.cumprod(1 + returns)

    sharpe_daily = PerformanceCalculatorDomainService.sharpe_ratio(equity, periods_per_year=365)
    sharpe_hourly = PerformanceCalculatorDomainService.sharpe_ratio(equity, periods_per_year=8760)

    # annual_return ∝ ppy, annual_std ∝ sqrt(ppy) → Sharpe ∝ sqrt(ppy).
    ratio = sharpe_hourly / sharpe_daily
    assert ratio == pytest.approx(np.sqrt(8760 / 365), rel=1e-9)


def test_sharpe_realistic_vol_is_bounded() -> None:
    # 1m equity with realistic crypto vol must yield |Sharpe| well under 10
    # (the old 365-constant annualization produced ~-227 on event-sampled data).
    rng = np.random.default_rng(42)
    n = 525600
    returns = rng.normal(0.30 / n, 0.60 / np.sqrt(n), n)
    equity = 100000.0 * np.cumprod(1 + returns)
    sharpe = PerformanceCalculatorDomainService.sharpe_ratio(
        equity, periods_per_year=Interval.MINUTE_1.periods_per_year
    )
    assert abs(sharpe) < 10


def test_sharpe_short_curve_returns_zero() -> None:
    assert (
        PerformanceCalculatorDomainService.sharpe_ratio(np.array([100.0]), periods_per_year=365)
        == 0.0
    )


def test_sharpe_nonzero_on_volatile_curve() -> None:
    # A curve with real, persistent variance must produce a finite, non-zero
    # Sharpe — the post-fix mark-to-market curve no longer flatlines between
    # fills, so this is the property the accounting fix restores.
    equity = np.array([100.0, 108.0, 103.0, 115.0, 110.0, 122.0, 118.0, 130.0])
    sharpe = PerformanceCalculatorDomainService.sharpe_ratio(equity, periods_per_year=365)
    assert np.isfinite(sharpe)
    assert sharpe != 0.0


def test_sharpe_guard_tolerates_zero_in_curve() -> None:
    # A 0 equity point (e.g. legacy all-in spot bug) must not raise or emit a
    # divide-by-zero RuntimeWarning; the np.divide guard maps that step to 0.
    equity = np.array([100.0, 0.0, 100.0, 110.0])
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        sharpe = PerformanceCalculatorDomainService.sharpe_ratio(equity, periods_per_year=365)
        sortino = PerformanceCalculatorDomainService.sortino_ratio(equity, periods_per_year=365)
    assert np.isfinite(sharpe)
    assert np.isfinite(sortino)


def test_cagr_unaffected_remains_calendar_based() -> None:
    # cagr must NOT take periods_per_year; it is calendar-day based.
    sig = inspect.signature(PerformanceCalculatorDomainService.cagr)
    assert "periods_per_year" not in sig.parameters
    # 10% over 365 days → 10% CAGR.
    assert PerformanceCalculatorDomainService.cagr(100.0, 110.0, 365) == pytest.approx(0.10)
