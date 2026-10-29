# The bootstrap reshuffles trade ORDER over the same PnL set to expose sequencing risk. It
# does not resample with replacement, so it says nothing about the tail of the PnL
# distribution itself.

from __future__ import annotations

import math

import numpy as np

from pocketquant.core.domain.trading.performance_calculator_domain_service import (
    PerformanceCalculatorDomainService as Perf,
)


# stdlib erf keeps scipy out of the dependencies.
def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def skewness(values: np.ndarray) -> float:
    v = np.asarray(values, dtype=float)
    if v.size < 3:
        return 0.0
    mean = np.mean(v)
    std = np.std(v)
    if std == 0:
        return 0.0
    return float(np.mean(((v - mean) / std) ** 3))


# Raw, not excess (normal = 3.0). The PSR formula uses raw kurtosis in its (kurt - 1) / 4
# term; excess kurtosis would shift the denominator and flip confidence.
def kurtosis(values: np.ndarray) -> float:
    v = np.asarray(values, dtype=float)
    if v.size < 4:
        return 3.0
    mean = np.mean(v)
    std = np.std(v)
    if std == 0:
        return 3.0
    return float(np.mean(((v - mean) / std) ** 4))


# A non-positive denominator (very high Sharpe with low kurtosis) collapses PSR to 0 or 1 by
# the sign of the numerator.
def psr(sharpe: float, skew: float, kurt: float, n: int, sr_star: float = 0.0) -> float:
    if n < 2:
        return 0.0
    variance_term = 1.0 - skew * sharpe + ((kurt - 1.0) / 4.0) * sharpe**2
    numerator = (sharpe - sr_star) * math.sqrt(n - 1)
    if variance_term <= 0:
        return 1.0 if numerator > 0 else 0.0
    z = numerator / math.sqrt(variance_term)
    return max(0.0, min(1.0, normal_cdf(z)))


# The p95-to-observed ratio is reported because realized drawdown often runs about 3x the
# backtest's.
def bootstrap_max_drawdown(
    trade_pnls: np.ndarray,
    initial_capital: float,
    n_iter: int = 1000,
    seed: int = 12345,
) -> dict[str, float]:
    pnls = np.asarray(trade_pnls, dtype=float)
    empty = {
        "observed_maxdd": 0.0,
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "ratio_p95_to_observed": 0.0,
    }
    if pnls.size < 2 or initial_capital <= 0:
        return empty

    def _maxdd(order: np.ndarray) -> float:
        equity = initial_capital + np.cumsum(order)
        equity = np.concatenate(([initial_capital], equity))
        return Perf.max_drawdown(equity)

    observed = _maxdd(pnls)

    rng = np.random.default_rng(seed)
    sims = np.empty(n_iter, dtype=float)
    for i in range(n_iter):
        sims[i] = _maxdd(rng.permutation(pnls))

    # maxDD is negative; the "worst" is the most negative → low percentiles.
    abs_sims = np.abs(sims)
    p50 = float(np.percentile(abs_sims, 50))
    p95 = float(np.percentile(abs_sims, 95))
    p99 = float(np.percentile(abs_sims, 99))
    obs_abs = abs(observed)
    return {
        "observed_maxdd": observed,
        "p50": -p50,
        "p95": -p95,
        "p99": -p99,
        "ratio_p95_to_observed": (p95 / obs_abs) if obs_abs > 0 else 0.0,
    }


# Basis caveat: the stored Sharpe is the annualized per-bar Sharpe of the equity curve,
# while skew, kurtosis and n come from per-trade net returns. PSR's sign is reliable (a
# negative Sharpe gives PSR about 0), but its magnitude mixes the two series: a directional
# signal, not a calibrated probability.
def compute_robustness(
    run_metrics: dict, per_trade_returns: np.ndarray, trade_pnls: np.ndarray,
    initial_capital: float, seed: int = 12345,
) -> dict[str, object]:
    sharpe = float(run_metrics.get("sharpe_ratio", 0.0))
    skew = skewness(per_trade_returns)
    kurt = kurtosis(per_trade_returns)
    n = int(per_trade_returns.size)
    return {
        "psr": psr(sharpe, skew, kurt, n),
        "skew": skew,
        "kurtosis": kurt,
        "sharpe_ratio": sharpe,
        "bootstrap_maxdd": bootstrap_max_drawdown(
            trade_pnls, initial_capital, seed=seed
        ),
    }
