# Stored pnl is GROSS (the engine tracks commission separately), so gross edge comes from
# the price move and net edge subtracts round-trip friction. That split separates a
# cost-killed strategy (gross > 0, net < 0) from a no-edge one (gross about 0).

from __future__ import annotations

import numpy as np

from scripts.rubric.types import TradeRow


def planned_rr(trade: TradeRow) -> float | None:
    if trade.sl_price is None or trade.tp_price is None:
        return None
    risk = abs(trade.entry_price - trade.sl_price)
    if risk == 0:
        return None
    return abs(trade.tp_price - trade.entry_price) / risk


def realized_r_multiple(trade: TradeRow) -> float | None:
    if trade.sl_price is None:
        return None
    risk = abs(trade.entry_price - trade.sl_price)
    if risk == 0:
        return None
    move = (
        trade.exit_price - trade.entry_price
        if trade.direction == "LONG"
        else trade.entry_price - trade.exit_price
    )
    return move / risk


def r_multiples(trades: list[TradeRow]) -> np.ndarray:
    vals = [r for t in trades if (r := realized_r_multiple(t)) is not None]
    return np.asarray(vals, dtype=float)


def _signed_move_bps(trade: TradeRow) -> float:
    if trade.entry_price == 0:
        return 0.0
    move = (
        trade.exit_price - trade.entry_price
        if trade.direction == "LONG"
        else trade.entry_price - trade.exit_price
    )
    return move / trade.entry_price * 1e4


def friction_bps(commission_bps: float, slippage_bps: float) -> float:
    return 2.0 * (commission_bps + slippage_bps)


def gross_vs_net_edge_bps(
    trades: list[TradeRow], commission_bps: float, slippage_bps: float
) -> dict[str, float]:
    if not trades:
        return {"gross_edge_bps": 0.0, "friction_bps": 0.0, "net_edge_bps": 0.0}
    gross = float(np.mean([_signed_move_bps(t) for t in trades]))
    fric = friction_bps(commission_bps, slippage_bps)
    return {
        "gross_edge_bps": gross,
        "friction_bps": fric,
        "net_edge_bps": gross - fric,
    }


def reconcile(
    trades: list[TradeRow], commission_bps: float, slippage_bps: float
) -> dict[str, float | None]:
    planned = [rr for t in trades if (rr := planned_rr(t)) is not None]
    realized = r_multiples(trades)
    edge = gross_vs_net_edge_bps(trades, commission_bps, slippage_bps)
    return {
        "planned_rr_median": float(np.median(planned)) if planned else None,
        "planned_rr_mean": float(np.mean(planned)) if planned else None,
        "realized_r_mean": float(np.mean(realized)) if realized.size else None,
        "realized_r_median": float(np.median(realized)) if realized.size else None,
        "expectancy_r": float(np.mean(realized)) if realized.size else None,
        **edge,
    }
