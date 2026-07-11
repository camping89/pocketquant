"""Shared dataclasses for the rubric pipeline — data holders, no logic.

Kept logic-free so every rubric module can import these without pulling in
Mongo, numpy, or scoring dependencies (avoids circular imports).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RunData:
    """One backtest run, loaded read-only from ``backtest_runs``.

    ``config_snapshot`` in Mongo stores every value as a string
    (``"10000.0"``, ``"0.5"``, ``"{}"``); the loader converts the numeric
    fields to float and ``parameters`` to a dict at the boundary, so the fields
    here are already typed.
    """

    run_id: str
    strategy_code: str
    symbol: str
    interval: str
    name: str | None
    initial_capital: float
    slippage_bps: float
    commission_bps: float
    start_date: datetime | None
    end_date: datetime | None
    parameters: dict[str, Any]
    metrics: dict[str, Any]
    # Equity curve points: {timestamp, equity, drawdown}. Trade-keyed (realized),
    # ~3.4k-4.5k points/run — NOT per-bar.
    equity_curve: list[dict[str, Any]]


@dataclass
class TradeRow:
    """One round-trip trade. All numerics are float, times are datetime —
    converted at the load boundary from the Mongo doc.
    """

    trade_id: str
    direction: str  # "LONG" | "SHORT"
    entry_price: float
    exit_price: float
    sl_price: float | None
    tp_price: float | None
    quantity: float
    pnl: float
    commission: float
    duration_seconds: float
    entry_time: datetime
    exit_time: datetime


@dataclass
class AxisScore:
    """One rubric axis: weighted 0-4 score, its letter grade, and the per-metric
    breakdown that produced it (value → band → points) so a renderer can explain
    every point.
    """

    name: str
    score: float  # 0-4
    grade: str  # A-F
    breakdown: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScorecardResult:
    """Full rubric outcome for one canonical run.

    ``overall_score`` is the weakest-axis minimum of the three axis scores; the
    axes carry their own breakdowns. ``aliases`` lists dedup'd duplicate run ids
    that this canonical run absorbs.
    """

    run_id: str
    strategy_code: str
    symbol: str
    interval: str
    name: str | None
    rubric_version: str
    axes: dict[str, AxisScore]  # "performance" | "robustness" | "design_integrity"
    overall_score: float  # 0-4, = min(axis scores)
    overall_grade: str  # A-F
    metrics: dict[str, Any]  # raw metric values (empirical + robustness)
    reconciliation: dict[str, Any]
    excursions: dict[str, Any]
    audit: dict[str, Any]
    diagnosis: str
    aliases: list[str] = field(default_factory=list)
