"""PerformanceCalculator Sharpe/Sortino — per-interval annualization.

Pins the keyword-only ``periods_per_year`` contract and known-curve → known-value
math, and that cagr stays calendar-based (unaffected by the interval change).
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from pocketquant.backtest.domain.services.performance_calculator import PerformanceCalculator
from pocketquant.core.domain.shared.enums import Interval


def test_periods_per_year_is_keyword_only() -> None:
    # Guards against a positional collision with risk_free_rate.
    sig = inspect.signature(PerformanceCalculator.sharpe_ratio)
    assert sig.parameters["periods_per_year"].kind is inspect.Parameter.KEYWORD_ONLY
    sig_s = inspect.signature(PerformanceCalculator.sortino_ratio)
    assert sig_s.parameters["periods_per_year"].kind is inspect.Parameter.KEYWORD_ONLY


def test_sharpe_zero_variance_returns_zero() -> None:
    # Exactly-constant returns → sample std 0 → guard returns 0.0.
    flat = np.array([100.0, 100.0, 100.0, 100.0])
    assert PerformanceCalculator.sharpe_ratio(flat, periods_per_year=365) == 0.0


def test_sharpe_known_curve_known_value() -> None:
    # Alternating returns +1% / -1% (approx): mean ~0 → Sharpe near 0.
    equity = np.array([100.0, 101.0, 100.0, 101.0, 100.0, 101.0])
    returns = np.diff(equity) / equity[:-1]
    mean, std = returns.mean(), returns.std(ddof=1)
    expected = (mean * 365) / (std * np.sqrt(365))
    assert PerformanceCalculator.sharpe_ratio(equity, periods_per_year=365) == pytest.approx(
        expected
    )


def test_sharpe_scales_with_sqrt_periods_per_year() -> None:
    rng = np.random.default_rng(7)
    returns = rng.normal(0.001, 0.01, 2000)
    equity = 100.0 * np.cumprod(1 + returns)

    sharpe_daily = PerformanceCalculator.sharpe_ratio(equity, periods_per_year=365)
    sharpe_hourly = PerformanceCalculator.sharpe_ratio(equity, periods_per_year=8760)

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
    sharpe = PerformanceCalculator.sharpe_ratio(
        equity, periods_per_year=Interval.MINUTE_1.periods_per_year
    )
    assert abs(sharpe) < 10


def test_sharpe_short_curve_returns_zero() -> None:
    assert PerformanceCalculator.sharpe_ratio(np.array([100.0]), periods_per_year=365) == 0.0


def test_cagr_unaffected_remains_calendar_based() -> None:
    # cagr must NOT take periods_per_year; it is calendar-day based.
    sig = inspect.signature(PerformanceCalculator.cagr)
    assert "periods_per_year" not in sig.parameters
    # 10% over 365 days → 10% CAGR.
    assert PerformanceCalculator.cagr(100.0, 110.0, 365) == pytest.approx(0.10)
