"""Extended performance metrics (quantstats formulas), plus an aggregator that
wires them to the domain ``PerformanceCalculatorDomainService`` so profit_factor,
drawdown and win/loss stats are never re-implemented.

Returns basis (fixed per plan validation S1):
- Distribution metrics (tail_ratio, gain_to_pain, SQN) use **per-trade net
  returns** — net_pnl / notional — because they describe the shape of realized
  trade outcomes.
- Drawdown metrics (ulcer, calmar, recovery, MAR) use the **equity curve** —
  they are peak-to-trough by construction.

profit_factor is reported GROSS (matches the stored metric): it signals whether
a raw edge exists before costs; cost_to_edge then shows whether costs erase it.
"""

from __future__ import annotations

import math

import numpy as np

from pocketquant.core.domain.trading.performance_calculator_domain_service import (
    PerformanceCalculatorDomainService as Perf,
)
from scripts.rubric.reconciliation import realized_r_multiple, reconcile
from scripts.rubric.types import RunData, TradeRow

_RISK_FREE = 0.0


def calmar(cagr: float, max_drawdown: float) -> float:
    if max_drawdown == 0:
        return 0.0
    return cagr / abs(max_drawdown)


def mar(total_return: float, max_drawdown: float) -> float:
    if max_drawdown == 0:
        return 0.0
    return total_return / abs(max_drawdown)


def ulcer_index(drawdown_series: np.ndarray) -> float:
    """sqrt(mean of squared drawdowns), scaled to percent. Uses (n-1) per the
    quantstats convention; 0 when fewer than 2 points.

    ``drawdown_series`` are negative decimals (e.g. -0.05 for a 5% drawdown).
    """
    dd = np.asarray(drawdown_series, dtype=float)
    if dd.size < 2:
        return 0.0
    pct = dd * 100.0
    return float(np.sqrt(np.sum(pct**2) / (dd.size - 1)))


def ulcer_performance_index(
    total_return: float, ulcer: float, risk_free: float = _RISK_FREE
) -> float:
    if ulcer == 0:
        return 0.0
    return (total_return * 100.0 - risk_free) / ulcer


def tail_ratio(returns: np.ndarray) -> float:
    """|p95 / p5| of the return distribution. ~1 is symmetric; <1 means the left
    tail (losses) is heavier than the right.
    """
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    p5 = np.percentile(r, 5)
    p95 = np.percentile(r, 95)
    if p5 == 0:
        return 0.0
    return float(abs(p95 / p5))


def common_sense_ratio(profit_factor: float, tail: float) -> float:
    return profit_factor * tail


def cpc_index(profit_factor: float, win_rate: float, win_loss_ratio: float) -> float:
    return profit_factor * win_rate * win_loss_ratio


def gain_to_pain(returns: np.ndarray) -> float:
    """Σ returns / |Σ negative returns| — total gain per unit of total loss."""
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    pain = abs(np.sum(r[r < 0]))
    if pain == 0:
        return 0.0
    return float(np.sum(r) / pain)


def recovery_factor(total_return: float, max_drawdown: float) -> float:
    """Net equity return over max drawdown (both on the equity basis)."""
    if max_drawdown == 0:
        return 0.0
    return abs(total_return) / abs(max_drawdown)


def kelly(win_rate: float, win_loss_ratio: float) -> float:
    """Kelly fraction: ((b·p) − q) / b, with b=win/loss ratio, p=win rate, q=1−p."""
    if win_loss_ratio == 0:
        return 0.0
    return (win_loss_ratio * win_rate - (1 - win_rate)) / win_loss_ratio


def risk_of_ruin(win_rate: float, n_trades: int) -> float:
    """((1−wr)/(1+wr))^n, computed in log-space to avoid underflow.

    The base is < 1 for any win_rate > 0, so this simple form saturates to ~0 at
    the trade counts here (>5k); it is a sanity floor, not a calibrated estimate.
    """
    if n_trades <= 0:
        return 1.0
    if win_rate <= 0:
        return 1.0
    if win_rate >= 1:
        return 0.0
    base = (1 - win_rate) / (1 + win_rate)
    if base <= 0:
        return 0.0
    return float(math.exp(n_trades * math.log(base)))


def sqn(r_multiples: np.ndarray) -> float:
    """System Quality Number: (mean R / std R) · sqrt(n). Needs ≥2 R-multiples."""
    r = np.asarray(r_multiples, dtype=float)
    if r.size < 2:
        return 0.0
    std = np.std(r, ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    return float((np.mean(r) / std) * math.sqrt(r.size))


def cost_to_edge(gross_edge_bps: float, friction_bps: float) -> float:
    """How many multiples of round-trip friction the gross edge covers. >1 means
    the edge survives costs. Signed: a negative gross edge yields a negative ratio.
    """
    if friction_bps == 0:
        return 0.0
    return gross_edge_bps / friction_bps


def _net_pnl_list(trades: list[TradeRow]) -> list[float]:
    return [t.pnl - t.commission for t in trades]


def _per_trade_returns(trades: list[TradeRow]) -> np.ndarray:
    """Net per-trade return as a fraction of notional (entry_price · quantity)."""
    out = []
    for t in trades:
        notional = t.entry_price * t.quantity
        if notional == 0:
            continue
        out.append((t.pnl - t.commission) / notional)
    return np.asarray(out, dtype=float)


def compute_metrics(run: RunData, trades: list[TradeRow]) -> dict[str, object]:
    """Assemble every empirical metric + reconciliation for one run.

    Domain ``Perf`` supplies profit_factor / drawdown / win-loss (DRY); this
    layer adds the extended ratios and the returns/drawdown basis split.
    """
    recon = reconcile(trades, run.commission_bps, run.slippage_bps)

    equity = np.array([p.get("equity", 0.0) for p in run.equity_curve], dtype=float)
    dd_series = Perf.drawdown_series(equity)
    max_dd = Perf.max_drawdown(equity)

    total_return = float(run.metrics.get("total_return", 0.0))
    cagr = float(run.metrics.get("cagr", 0.0))
    win_rate = float(run.metrics.get("win_rate", 0.0))

    gross_pnl = [t.pnl for t in trades]
    gross_profit = sum(p for p in gross_pnl if p > 0)
    gross_loss = abs(sum(p for p in gross_pnl if p < 0))
    profit_factor = Perf.profit_factor(gross_profit, gross_loss)

    net_pnl = _net_pnl_list(trades)
    avg_win, avg_loss, _, _ = Perf.average_win_loss(net_pnl)
    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

    returns = _per_trade_returns(trades)
    r_mult = np.array(
        [r for t in trades if (r := realized_r_multiple(t)) is not None], dtype=float
    )

    ui = ulcer_index(dd_series)
    tail = tail_ratio(returns)

    return {
        # Drawdown-based (equity curve)
        "max_drawdown": max_dd,
        "calmar": calmar(cagr, max_dd),
        "mar": mar(total_return, max_dd),
        "ulcer_index": ui,
        "ulcer_performance_index": ulcer_performance_index(total_return, ui),
        # Drawdown-based: net equity return over max drawdown (same equity basis
        # as max_dd — NOT the sum of per-trade notional-fraction returns).
        "recovery_factor": recovery_factor(total_return, max_dd),
        # Distribution-based (per-trade net returns)
        "tail_ratio": tail,
        "gain_to_pain": gain_to_pain(returns),
        "common_sense_ratio": common_sense_ratio(profit_factor, tail),
        "cpc_index": cpc_index(profit_factor, win_rate, win_loss_ratio),
        "sqn": sqn(r_mult),
        "kelly": kelly(win_rate, win_loss_ratio),
        "risk_of_ruin": risk_of_ruin(win_rate, len(trades)),
        # Cost — edge/friction are always float from gross_vs_net_edge_bps.
        "cost_to_edge": cost_to_edge(
            float(recon["gross_edge_bps"] or 0.0), float(recon["friction_bps"] or 0.0)
        ),
        # Passthrough context
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "win_loss_ratio": win_loss_ratio,
        "total_return": total_return,
        "cagr": cagr,
        "sharpe_ratio": float(run.metrics.get("sharpe_ratio", 0.0)),
        "sortino_ratio": float(run.metrics.get("sortino_ratio", 0.0)),
        "total_trades": len(trades),
        "reconciliation": recon,
    }
