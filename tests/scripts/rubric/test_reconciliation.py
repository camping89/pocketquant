"""Pure-math tests for reconciliation — planned R:R, realized R, edge split."""

from __future__ import annotations

from datetime import datetime

from scripts.rubric.reconciliation import (
    friction_bps,
    gross_vs_net_edge_bps,
    planned_rr,
    realized_r_multiple,
)
from scripts.rubric.types import TradeRow

_T0 = datetime(2025, 1, 1, 0, 0, 0)
_T1 = datetime(2025, 1, 1, 0, 10, 0)


def _trade(**kw) -> TradeRow:
    base = dict(
        trade_id="t",
        direction="LONG",
        entry_price=100.0,
        exit_price=100.0,
        sl_price=98.0,
        tp_price=104.0,
        quantity=1.0,
        pnl=0.0,
        commission=0.0,
        duration_seconds=600.0,
        entry_time=_T0,
        exit_time=_T1,
    )
    base.update(kw)
    return TradeRow(**base)


def test_planned_rr_long():
    # tp 104, entry 100, sl 98 → reward 4, risk 2 → 2.0
    assert planned_rr(_trade()) == 2.0


def test_planned_rr_none_without_levels():
    assert planned_rr(_trade(sl_price=None)) is None
    assert planned_rr(_trade(tp_price=None)) is None
    assert planned_rr(_trade(sl_price=100.0)) is None  # zero risk


def test_realized_r_long_win():
    # exit 102, entry 100, risk 2 → +1R
    assert realized_r_multiple(_trade(exit_price=102.0)) == 1.0


def test_realized_r_short_win():
    # SHORT: entry 100, exit 98, sl 102 → move +2, risk 2 → +1R
    t = _trade(direction="SHORT", entry_price=100.0, exit_price=98.0, sl_price=102.0)
    assert realized_r_multiple(t) == 1.0


def test_realized_r_none_without_sl():
    assert realized_r_multiple(_trade(sl_price=None)) is None


def test_friction_round_trip():
    # commission 3 + slippage 0.5, round trip → 2*(3.5) = 7.0
    assert friction_bps(3.0, 0.5) == 7.0


def test_gross_vs_net_split_cost_killed():
    # gross positive move but friction larger → net negative (cost-killed shape)
    trades = [_trade(exit_price=100.05) for _ in range(10)]  # +5 bps gross
    out = gross_vs_net_edge_bps(trades, commission_bps=3.0, slippage_bps=0.5)
    assert out["gross_edge_bps"] > 0
    assert out["friction_bps"] == 7.0
    assert out["net_edge_bps"] < 0


def test_gross_vs_net_empty():
    out = gross_vs_net_edge_bps([], 3.0, 0.5)
    assert out == {"gross_edge_bps": 0.0, "friction_bps": 0.0, "net_edge_bps": 0.0}
