"""Validate the 3 finalists across BTC/ETH/SOL — the decisive multi-asset test.

The 260712 report's #1 unresolved question: do the 3 variants generalize beyond
BTC-2025, or are they a single-asset single-regime artifact? Same config, same
walk-forward split, per-symbol cache. A variant is "generalizing" only if OOS
net@taker stays positive on symbols it was never tuned on.

Reports per (symbol x variant): IN/OUT net@taker, n, win rate, and outlier
robustness (drop top-3 winners). Prints a compact cross-asset matrix at the end.
"""

from __future__ import annotations

import numpy as np

import pq_structure_lib as S

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

FINALISTS = [
    ("A conservative", dict(prox_bps=60, min_rr=1.5, tp_rr=3.0, wick_pct=0.5)),
    ("B balanced", dict(prox_bps=100, min_rr=1.3, tp_rr=3.0, wick_pct=0.6)),
    ("C wide-RR", dict(prox_bps=120, min_rr=1.3, tp_rr=4.0, wick_pct=0.6)),
]


def eval_one(code: str, params: dict) -> dict:
    S.use_cache(f"/tmp/pq_cache_{code}")
    e = S.build_structure_entries(
        tf="1h", struct_tf="1d", trend_tf="1d", trend_span=20,
        prox_bps=params["prox_bps"], min_rr=params["min_rr"],
        wick_pct=params["wick_pct"], tp_rr=params["tp_rr"],
    )
    if len(e["idx"]) < 8:
        return dict(n_out=0)
    bps = S.first_touch_levels(e, "1h")
    ep = e["epoch"][: len(bps)]
    xin, xout = bps[ep < S.SPLIT_EPOCH], bps[ep >= S.SPLIT_EPOCH]
    din = S.summarize(xin, "taker")
    dout = S.summarize(xout, "taker")
    xo = np.sort(xout)[::-1]
    drop3 = (xo[3:].mean() - 10.0) if len(xo) > 3 else float("nan")
    return dict(
        n_in=din.get("n", 0), n_out=dout.get("n", 0),
        net_in=din.get("net", float("nan")), net_out=dout.get("net", float("nan")),
        wr_out=dout.get("wr", float("nan")), drop3_out=drop3,
    )


if __name__ == "__main__":
    print("=" * 100)
    print("MULTI-SYMBOL VALIDATION — 1h engulfing / 1d trend+level / fixed-RR, split 2026-01-06")
    print("=" * 100)
    matrix = {}
    for name, params in FINALISTS:
        print(f"\n### {name}  {params}")
        for code in SYMBOLS:
            r = eval_one(code, params)
            matrix[(name, code)] = r
            if r["n_out"] == 0:
                print(f"  {code:8} — no data / too few entries")
                continue
            print(
                f"  {code:8} IN net={r['net_in']:+7.1f}(n={r['n_in']:3})  "
                f"OUT net={r['net_out']:+7.1f}(n={r['n_out']:3}) wr={r['wr_out']:.2f}  "
                f"drop3_out={r['drop3_out']:+7.1f}"
            )
    print("\n" + "=" * 100)
    print("CROSS-ASSET OOS net@taker MATRIX (positive on all 3 = generalizes):")
    print(f"{'variant':18}" + "".join(f"{c:>12}" for c in SYMBOLS))
    for name, _ in FINALISTS:
        row = f"{name:18}"
        for code in SYMBOLS:
            r = matrix[(name, code)]
            row += f"{r.get('net_out', float('nan')):>12.1f}" if r["n_out"] else f"{'--':>12}"
        print(row)
