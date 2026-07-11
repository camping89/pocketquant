"""Threshold-based scoring: raw metrics → 0-4 per metric → weighted-sum per axis
→ A-F, with the overall grade taken as the weakest axis (min).

Two aggregation levels, deliberately different:
- metric → axis: weighted sum (each axis a blend of its metrics).
- axis → overall: MIN (weakest-axis dominates). A robustness F drags the whole
  run down even with A-grade performance — a weighted average would hide the F.

Bands are step functions over the raw value (first band whose upper bound the
value falls under). This expresses higher-better (calmar), lower-better (ulcer,
degrees_of_freedom), and range-optimal (mae_to_stop, best in 0.6-0.85) shapes
uniformly. Thresholds are industry references (see docs/backtest-rubric/
methodology.md); bump RUBRIC_VERSION when any band or weight changes.

Crypto-1m caveat: these thresholds originate from equity/daily research. On 1m
crypto they are directional, not calibrated — carried in output metadata.
"""

from __future__ import annotations

import math

from scripts.rubric.types import AxisScore, ScorecardResult

RUBRIC_VERSION = "1.0.0"

_INF = math.inf

# metric → ascending list of (upper_bound_exclusive, points). The value scores as
# the first band it falls under; the final band's bound is +inf.
THRESHOLDS: dict[str, list[tuple[float, int]]] = {
    # Performance (higher better, except ulcer)
    "calmar": [(0, 0), (1, 1), (2, 2), (3, 3), (_INF, 4)],
    "mar": [(0, 0), (0.5, 1), (1, 2), (2, 3), (_INF, 4)],
    "ulcer_index": [(2, 4), (5, 3), (10, 2), (15, 1), (_INF, 0)],  # lower better
    "ulcer_performance_index": [(0, 0), (0.5, 1), (1, 2), (2, 3), (_INF, 4)],
    "recovery_factor": [(0.5, 0), (1, 1), (2, 2), (3, 3), (_INF, 4)],
    # Robustness
    "psr": [(0.5, 0), (0.75, 1), (0.9, 2), (0.95, 3), (_INF, 4)],
    "sqn": [(1, 0), (1.6, 1), (2, 2), (3, 3), (_INF, 4)],
    "tail_ratio": [(0.8, 0), (1.0, 1), (1.2, 2), (1.5, 3), (_INF, 4)],
    "common_sense_ratio": [(0.8, 0), (1.0, 1), (1.5, 2), (2.0, 3), (_INF, 4)],
    "gain_to_pain": [(0, 0), (0.5, 1), (1.0, 2), (1.5, 3), (_INF, 4)],
    # Design-integrity
    "cost_to_edge": [(0.5, 0), (0.8, 1), (1.0, 2), (1.25, 3), (_INF, 4)],
    "mfe_capture": [(0.3, 0), (0.45, 1), (0.6, 2), (0.75, 3), (_INF, 4)],
    # range-optimal bell: calibrated in 0.6-0.85; too wide (<0.5) or too tight (>1)
    "mae_to_stop": [(0.5, 1), (0.6, 3), (0.85, 4), (1.0, 2), (_INF, 1)],
    # Gray-penalty: more tunable params → higher overfit risk (lower better).
    # Integer DoF: ≤3→4, 4-5→3, 6-7→2, 8-9→1, ≥10→0.
    "degrees_of_freedom": [(4, 4), (6, 3), (8, 2), (10, 1), (_INF, 0)],
}

# axis → {metric: weight}. Weights sum to 1 per axis; a metric that scores N/A is
# dropped and the remaining weights are re-normalized.
WEIGHTS: dict[str, dict[str, float]] = {
    "performance": {
        "calmar": 0.25,
        "mar": 0.25,
        "ulcer_index": 0.25,
        "ulcer_performance_index": 0.15,
        "recovery_factor": 0.10,
    },
    "robustness": {
        "psr": 0.30,
        "sqn": 0.25,
        "tail_ratio": 0.15,
        "common_sense_ratio": 0.15,
        "gain_to_pain": 0.15,
    },
    "design_integrity": {
        "cost_to_edge": 0.35,
        "degrees_of_freedom": 0.25,
        "mfe_capture": 0.20,
        "mae_to_stop": 0.20,
    },
}


def score_metric(name: str, value: float | None) -> int | None:
    """Map a raw value to 0-4 via its threshold bands. None (metric N/A) → None."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    bands = THRESHOLDS.get(name)
    if bands is None:
        return None
    for upper, points in bands:
        if value < upper:
            return points
    return bands[-1][1]


def grade_from_score(score: float) -> str:
    if score >= 3.5:
        return "A"
    if score >= 2.5:
        return "B"
    if score >= 1.5:
        return "C"
    if score >= 0.5:
        return "D"
    return "F"


def score_axis(axis: str, values: dict[str, float | None]) -> AxisScore:
    """Weighted-sum the axis's metrics; drop N/A metrics and re-normalize weights."""
    weights = WEIGHTS[axis]
    breakdown: list[dict] = []
    weighted_sum = 0.0
    active_weight = 0.0
    for metric, weight in weights.items():
        raw = values.get(metric)
        points = score_metric(metric, raw)
        breakdown.append(
            {"metric": metric, "value": raw, "points": points, "weight": weight}
        )
        if points is None:
            continue
        weighted_sum += points * weight
        active_weight += weight

    score = weighted_sum / active_weight if active_weight > 0 else 0.0
    return AxisScore(
        name=axis, score=score, grade=grade_from_score(score), breakdown=breakdown
    )


def _diagnose(values: dict[str, float | None], axes: dict[str, AxisScore]) -> str:
    """Short plain-language read of the dominant failure mode."""
    gross = values.get("gross_edge_bps")
    net = values.get("net_edge_bps")
    psr = values.get("psr")
    parts: list[str] = []
    if gross is not None and net is not None:
        # A gross edge under ~1 bp is indistinguishable from zero at this
        # frequency (master-report: raw edge ≈ -0.7 bps "not distinguishable
        # from zero") — call it no-edge before blaming costs.
        if abs(gross) < 1.0:
            parts.append("no directional edge: gross edge ≈ 0 before costs")
        elif gross > 0 and net < 0:
            parts.append("cost-killed: gross edge positive but costs erase it")
        elif net < 0:
            parts.append("net-negative after costs")
    if psr is not None and psr < 0.5:
        parts.append("statistically unreliable (PSR < 0.5)")
    if not parts:
        parts.append(f"overall grade {axes_min_grade(axes)}")
    return "; ".join(parts)


def axes_min_grade(axes: dict[str, AxisScore]) -> str:
    weakest = min(axes.values(), key=lambda a: a.score)
    return weakest.grade


def score_run(
    *,
    run_id: str,
    strategy_code: str,
    symbol: str,
    interval: str,
    name: str | None,
    metrics: dict,
    robustness: dict,
    excursions: dict,
    audit: dict,
    aliases: list[str] | None = None,
) -> ScorecardResult:
    """Assemble the full scorecard. ``overall = min(axis scores)`` (weakest-axis)."""
    reconciliation = metrics.get("reconciliation", {})
    values: dict[str, float | None] = {
        **{k: v for k, v in metrics.items() if isinstance(v, (int, float))},
        "psr": robustness.get("psr"),
        "mfe_capture": excursions.get("mfe_capture_mean"),
        "mae_to_stop": excursions.get("mae_to_stop_mean"),
        "degrees_of_freedom": audit.get("degrees_of_freedom"),
        "gross_edge_bps": reconciliation.get("gross_edge_bps"),
        "net_edge_bps": reconciliation.get("net_edge_bps"),
    }

    axes = {
        "performance": score_axis("performance", values),
        "robustness": score_axis("robustness", values),
        "design_integrity": score_axis("design_integrity", values),
    }
    overall_score = min(a.score for a in axes.values())

    return ScorecardResult(
        run_id=run_id,
        strategy_code=strategy_code,
        symbol=symbol,
        interval=interval,
        name=name,
        rubric_version=RUBRIC_VERSION,
        axes=axes,
        overall_score=overall_score,
        overall_grade=grade_from_score(overall_score),
        metrics={k: v for k, v in metrics.items() if k != "reconciliation"},
        reconciliation=reconciliation,
        excursions=excursions,
        audit=audit,
        diagnosis=_diagnose(values, axes),
        aliases=aliases or [],
    )
