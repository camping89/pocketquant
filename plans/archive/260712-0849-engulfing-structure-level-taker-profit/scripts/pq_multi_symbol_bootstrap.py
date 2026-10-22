"""Bootstrap CI companion to pq_multi_symbol_validate.py (kill-criterion #3).

The validate script prints point-estimate OOS net@taker per (symbol x variant)
but no interval. This computes per-symbol OOS 95% bootstrap CI and the POOLED CI
(BTC+ETH+SOL OOS trades concatenated) — the core of Test B: if the edge is real,
pooling ~3x trades should shrink the CI and pull it off zero. Same config, same
split, same taker friction (10 bps RT) as the validate script.
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
FR = 10.0  # taker round-trip
B = 5000
rng = np.random.default_rng(42)


def oos_bps(code: str, params: dict) -> np.ndarray:
    """OOS gross bps per trade for one symbol x variant."""
    S.use_cache(f"/tmp/pq_cache_{code}")
    e = S.build_structure_entries(
        tf="1h", struct_tf="1d", trend_tf="1d", trend_span=20,
        prox_bps=params["prox_bps"], min_rr=params["min_rr"],
        wick_pct=params["wick_pct"], tp_rr=params["tp_rr"],
    )
    if len(e["idx"]) < 8:
        return np.array([])
    bps = S.first_touch_levels(e, "1h")
    ep = e["epoch"][: len(bps)]
    return bps[ep >= S.SPLIT_EPOCH]


def ci(x: np.ndarray) -> tuple[float, float, float]:
    """Net@taker point + 95% bootstrap CI on the mean net."""
    if len(x) == 0:
        return (float("nan"),) * 3
    means = np.array([rng.choice(x, len(x), replace=True).mean() for _ in range(B)])
    net = x.mean() - FR
    lo, hi = np.percentile(means - FR, [2.5, 97.5])
    return net, lo, hi


if __name__ == "__main__":
    print("=" * 92)
    print("OOS net@taker 95% BOOTSTRAP CI — per-symbol + POOLED (kill-criterion #3)")
    print("=" * 92)
    for name, params in FINALISTS:
        print(f"\n### {name}  {params}")
        pool = []
        for code in SYMBOLS:
            x = oos_bps(code, params)
            pool.append(x)
            net, lo, hi = ci(x)
            flag = "" if len(x) == 0 else ("  CI>0" if lo > 0 else ("  CI<0" if hi < 0 else "  CI spans 0"))
            print(f"  {code:8} n={len(x):3}  net={net:+7.1f}  95%CI=[{lo:+7.1f}, {hi:+7.1f}]{flag}")
        allx = np.concatenate([p for p in pool if len(p)])
        net, lo, hi = ci(allx)
        flag = "  CI>0" if lo > 0 else ("  CI<0" if hi < 0 else "  CI spans 0")
        print(f"  {'POOLED':8} n={len(allx):3}  net={net:+7.1f}  95%CI=[{lo:+7.1f}, {hi:+7.1f}]{flag}")
