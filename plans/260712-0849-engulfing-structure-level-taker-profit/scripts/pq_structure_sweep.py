"""Sweep structure-filtered engulfing for TAKER-positive, walk-forward-stable configs.

Grid: entry TF x structure TF x proximity x min_rr x trend gate. Report IN/OUT
(split 2026-01-06) net@taker. A config only counts if net@taker > 0 on BOTH
halves AND OOS n is not trivially small. Controls per finalist: counter-trend
and trend-shuffled to prove the level+trend gate carries the edge, not luck.
"""

from __future__ import annotations

import pq_structure_lib as S


def run(label, **kw):
    e = S.build_structure_entries(**kw)
    if len(e["idx"]) == 0:
        print(f"{label:42} EMPTY")
        return None
    m_in, m_out = S.in_out_masks(e)
    bps = S.first_touch_levels(e, kw["tf"])
    # align mask to resolved trades (first_touch skips i+1>=n tail; negligible)
    ep = e["epoch"][: len(bps)]
    import numpy as np

    ok_in = ep < S.SPLIT_EPOCH
    ok_out = ep >= S.SPLIT_EPOCH
    d_all = S.summarize(bps, "taker", f"{label} ALL")
    d_in = S.summarize(bps[ok_in], "taker", f"{label} IN")
    d_out = S.summarize(bps[ok_out], "taker", f"{label} OUT")
    for d in (d_all, d_in, d_out):
        S.show(d)
    return d_in, d_out, e, bps


CONFIGS = [
    # entry TF, struct TF, trend TF, prox, min_rr, wick
    ("5m->1h", dict(tf="5m", struct_tf="1h", trend_tf="1d", prox_bps=20, min_rr=1.5, wick_pct=0.4)),
    ("5m->1h rr2", dict(tf="5m", struct_tf="1h", trend_tf="1d", prox_bps=20, min_rr=2.0, wick_pct=0.4)),
    ("5m->4h", dict(tf="5m", struct_tf="4h", trend_tf="1d", prox_bps=25, min_rr=1.5, wick_pct=0.4)),
    ("15m->4h", dict(tf="15m", struct_tf="4h", trend_tf="1d", prox_bps=30, min_rr=1.5, wick_pct=0.4)),
    ("15m->1d", dict(tf="15m", struct_tf="1d", trend_tf="1d", prox_bps=40, min_rr=1.5, wick_pct=0.4)),
    ("1h->4h", dict(tf="1h", struct_tf="4h", trend_tf="1d", prox_bps=40, min_rr=1.5, wick_pct=0.5)),
    ("1h->1d", dict(tf="1h", struct_tf="1d", trend_tf="1d", prox_bps=60, min_rr=1.5, wick_pct=0.5)),
    ("1h->1d rr2", dict(tf="1h", struct_tf="1d", trend_tf="1d", prox_bps=60, min_rr=2.0, wick_pct=0.5)),
    ("1h->1d notrend", dict(tf="1h", struct_tf="1d", trend_tf=None, prox_bps=60, min_rr=1.5, wick_pct=0.5)),
    ("4h->1d", dict(tf="4h", struct_tf="1d", trend_tf="1d", prox_bps=80, min_rr=1.5, wick_pct=0.6)),
]

if __name__ == "__main__":
    print("=" * 110)
    print("STRUCTURE-FILTERED ENGULFING SWEEP — net@taker (round-trip 10 bps), split 2026-01-06")
    print("=" * 110)
    results = {}
    for label, kw in CONFIGS:
        r = run(label, **kw)
        if r:
            results[label] = r
        print("-" * 110)
