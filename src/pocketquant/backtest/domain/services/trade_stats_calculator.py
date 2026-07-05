"""Pure trade-statistics calculators for the backtest result view.

Distribution + streak + profit-factor + drawdown-period analytics that the FE
used to compute over the full trade list. Centralized here so the browser loads
numbers instead of raw trades. Static/free functions, no I/O — mirrors the
``PerformanceCalculatorDomainService`` convention.

Semantics match the former FE implementation exactly (same edge cases) so the
result view is visually identical after the move.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pocketquant.core.domain.backtest.value_objects import EquityPoint


@dataclass
class HistogramBin:
    """A single bucket: half-open [lo, hi) range and the count inside it."""

    lo: float
    hi: float
    count: int


@dataclass
class StreakStats:
    max_win_streak: int
    max_loss_streak: int


@dataclass
class DirectionProfitFactor:
    """Profit factor split by side; ``None`` when a side has no losing PnL."""

    long: float | None
    short: float | None


@dataclass
class DrawdownPeriod:
    """One peak-to-trough episode read off the equity curve's per-point drawdown."""

    depth: float  # negative fraction, e.g. -0.18
    start_time: datetime
    trough_time: datetime
    recovery_time: datetime | None  # None while still under water
    duration_seconds: float


def histogram(values: list[float], bin_count: int = 20) -> list[HistogramBin]:
    """Bucket ``values`` into ``bin_count`` equal-width bins over [min, max].

    Empty input -> []. A degenerate range (all equal) collapses to one bin. The
    top edge is clamped into the last bin so ``max`` isn't dropped by the
    half-open range.
    """
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if lo == hi:
        return [HistogramBin(lo=lo, hi=hi, count=len(values))]

    width = (hi - lo) / bin_count
    bins = [
        HistogramBin(lo=lo + i * width, hi=lo + (i + 1) * width, count=0)
        for i in range(bin_count)
    ]
    for v in values:
        idx = min(bin_count - 1, int((v - lo) / width))
        bins[idx].count += 1
    return bins


def win_loss_streaks(pnls: list[float]) -> StreakStats:
    """Longest consecutive win / loss run over closed trades in order.

    Break-even (pnl == 0) resets both streaks. Caller passes closed-trade PnL in
    chronological order (open positions are excluded upstream).
    """
    max_win = max_loss = cur_win = cur_loss = 0
    for pnl in pnls:
        if pnl > 0:
            cur_win += 1
            cur_loss = 0
            max_win = max(max_win, cur_win)
        elif pnl < 0:
            cur_loss += 1
            cur_win = 0
            max_loss = max(max_loss, cur_loss)
        else:
            cur_win = cur_loss = 0
    return StreakStats(max_win_streak=max_win, max_loss_streak=max_loss)


def profit_factor_by_direction(
    entries: list[tuple[str, float]],
) -> DirectionProfitFactor:
    """Gross-profit / gross-loss per direction over closed trades.

    ``entries`` is ``(direction, pnl)`` pairs. A side with no losing PnL yields
    ``None`` (factor undefined / infinite) — the FE renders that as ∞.
    """
    acc = {"LONG": {"profit": 0.0, "loss": 0.0}, "SHORT": {"profit": 0.0, "loss": 0.0}}
    for direction, pnl in entries:
        side = acc.get(direction)
        if side is None:
            continue
        if pnl >= 0:
            side["profit"] += pnl
        else:
            side["loss"] += abs(pnl)

    def factor(s: dict[str, float]) -> float | None:
        return s["profit"] / s["loss"] if s["loss"] > 0 else None

    return DirectionProfitFactor(long=factor(acc["LONG"]), short=factor(acc["SHORT"]))


def drawdown_periods(curve: list[EquityPoint], top_n: int = 5) -> list[DrawdownPeriod]:
    """Top-N deepest drawdown episodes scanned from per-point drawdown.

    A period opens when drawdown goes negative, tracks its deepest point, and
    closes when equity reclaims the prior peak (drawdown back to >= 0). An
    unrecovered tail period has ``recovery_time = None``. Sorted deepest first.
    """
    periods: list[DrawdownPeriod] = []
    open_start: datetime | None = None
    open_trough: datetime | None = None
    open_depth = 0.0

    for pt in curve:
        if pt.drawdown < 0:
            if open_start is None:
                open_start = pt.timestamp
                open_trough = pt.timestamp
                open_depth = pt.drawdown
            elif pt.drawdown < open_depth:
                open_depth = pt.drawdown
                open_trough = pt.timestamp
        elif open_start is not None:
            periods.append(
                DrawdownPeriod(
                    depth=open_depth,
                    start_time=open_start,
                    trough_time=open_trough,  # type: ignore[arg-type]
                    recovery_time=pt.timestamp,
                    duration_seconds=(pt.timestamp - open_start).total_seconds(),
                )
            )
            open_start = open_trough = None
            open_depth = 0.0

    if open_start is not None and curve:
        last = curve[-1]
        periods.append(
            DrawdownPeriod(
                depth=open_depth,
                start_time=open_start,
                trough_time=open_trough,  # type: ignore[arg-type]
                recovery_time=None,
                duration_seconds=(last.timestamp - open_start).total_seconds(),
            )
        )

    periods.sort(key=lambda p: p.depth)
    return periods[:top_n]
