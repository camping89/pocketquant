# Logic-free so every rubric module can import these without pulling in Mongo, numpy or
# scoring, which avoids circular imports.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# config_snapshot stores every value as a string; the loader converts them at the boundary,
# so these fields are already typed.
@dataclass
class RunData:
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
    name: str
    score: float  # 0-4
    grade: str  # A-F
    breakdown: list[dict[str, Any]] = field(default_factory=list)


# `aliases` are the duplicate run ids this canonical run absorbs.
@dataclass
class ScorecardResult:
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
