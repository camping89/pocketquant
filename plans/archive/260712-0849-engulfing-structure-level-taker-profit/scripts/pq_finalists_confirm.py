"""Confirm 3 finalists with full honesty checks:
- IN/OUT net@taker AND net@maker
- exit mix, win rate, median vs mean (outlier robustness), max single-trade
- counter-trend control (must collapse)
- FAIR engulfing-vs-random at identical prox/rr (engulfing's marginal lift)
The 3 finalists share ONE mechanism (1h engulfing trigger, 1d trend gate, 1d
structure level, fixed-RR exit); they differ by proximity/RR risk profile.
"""

from __future__ import annotations

import numpy as np

import pq_structure_lib as S


def full_stats(e, tf, tag):
    bps, kind = S.first_touch_levels(e, tf, with_exits=True)
    ep = e["epoch"][: len(bps)]
    oi, oo = ep < S.SPLIT_EPOCH, ep >= S.SPLIT_EPOCH
    mix = np.bincount(kind, minlength=3)
    for half, m in (("IN", oi), ("OUT", oo)):
        x = bps[m]
        if len(x) == 0:
            print(f"  {tag} {half}: n=0")
            continue
        t = S.summarize(x, "taker")
        mk = S.summarize(x, "maker")
        print(
            f"  {tag} {half}: n={len(x):3} wr={t['wr']:.2f} "
            f"gross={t['gross']:+6.1f} net@taker={t['net']:+6.1f} net@maker={mk['net']:+6.1f} "
            f"median={np.median(x):+6.1f} max={x.max():+6.0f} min={x.min():+6.0f}"
        )
    print(f"     exit SL/TP/mark = {mix[0]}/{mix[1]}/{mix[2]}  total n={len(bps)}")


def counter(tf, struct_tf, trend_tf, prox, rr_f, tp_rr, span, wick):
    e = S.build_structure_entries(
        tf=tf, struct_tf=struct_tf, trend_tf=None, prox_bps=prox,
        min_rr=rr_f, wick_pct=wick, tp_rr=tp_rr,
    )
    keep = []
    for j in range(len(e["idx"])):
        up = S.trend_up_at(trend_tf, int(e["epoch"][j]), span=span)
        if up is None:
            keep.append(False); continue
        isl = bool(e["islong"][j])
        keep.append(not ((isl and up) or ((not isl) and (not up))))
    keep = np.array(keep, dtype=bool)
    ec = {k: (v[keep] if isinstance(v, np.ndarray) and len(v) == len(keep) else v) for k, v in e.items()}
    if len(ec["idx"]) < 8:
        print(f"  counter n={len(ec['idx'])} (too few)"); return
    bps = S.first_touch_levels(ec, tf)
    ep = ec["epoch"][: len(bps)]
    S.show(S.summarize(bps[ep < S.SPLIT_EPOCH], "taker", "  counter IN"))
    S.show(S.summarize(bps[ep >= S.SPLIT_EPOCH], "taker", "  counter OUT"))


def random_same_gate(prox, tp_rr, span, frac, seed=7):
    """Random 1h bar, same 1d trend+level gate, same fixed-RR. Marginal-lift control."""
    b = S.load_bars("1h"); H, L, C, ts = b["h"], b["l"], b["c"], b["ts"]
    rng = np.random.default_rng(seed)
    idxs, prices, islongs, epochs, sls, tps = [], [], [], [], [], []
    for i in range(1, len(C)):
        e = int(ts[i])
        up = S.trend_up_at("1d", e, span=span)
        if up is None or rng.random() > frac:
            continue
        ep = float(C[i]); hp, lp = S.levels_before("1d", e, k=3)
        if len(lp) == 0 and len(hp) == 0:
            continue
        isl = bool(up)
        if isl:
            sup = S.nearest_support(lp, hp, ep)
            if sup is None or not (-prox <= (float(L[i]) - sup) / ep * 1e4 <= prox):
                continue
            sl = sup * (1 - 5 / 1e4)
            if sl >= ep:
                continue
            tp = ep + tp_rr * (ep - sl)
        else:
            res = S.nearest_resistance(lp, hp, ep)
            if res is None or not (-prox <= (res - float(H[i])) / ep * 1e4 <= prox):
                continue
            sl = res * (1 + 5 / 1e4)
            if sl <= ep:
                continue
            tp = ep - tp_rr * (sl - ep)
        idxs.append(i); prices.append(ep); islongs.append(isl); epochs.append(e); sls.append(sl); tps.append(tp)
    ec = dict(idx=np.array(idxs), price=np.array(prices), islong=np.array(islongs, dtype=bool),
              epoch=np.array(epochs, dtype="int64"), sl=np.array(sls), tp=np.array(tps))
    bps = S.first_touch_levels(ec, "1h")
    ep = ec["epoch"][: len(bps)]
    out = S.summarize(bps[ep >= S.SPLIT_EPOCH], "taker")
    return out


FINALISTS = [
    ("A conservative", dict(prox_bps=60, rr_f=1.5, tp_rr=3.0, span=20, wick=0.5)),
    ("B balanced",     dict(prox_bps=100, rr_f=1.3, tp_rr=3.0, span=20, wick=0.6)),
    ("C wide-RR",      dict(prox_bps=120, rr_f=1.3, tp_rr=4.0, span=20, wick=0.6)),
]

if __name__ == "__main__":
    print("=" * 104)
    print("3 FINALISTS — 1h engulfing trigger / 1d trend gate / 1d swing level / fixed-RR exit")
    print("=" * 104)
    for name, p in FINALISTS:
        print(f"\n### {name}  prox={p['prox_bps']} tp_rr={p['tp_rr']} span={p['span']} wick={p['wick']}")
        e = S.build_structure_entries(
            tf="1h", struct_tf="1d", trend_tf="1d",
            prox_bps=p["prox_bps"], min_rr=p["rr_f"], wick_pct=p["wick"],
            trend_span=p["span"], tp_rr=p["tp_rr"],
        )
        full_stats(e, "1h", name)
        counter("1h", "1d", "1d", p["prox_bps"], p["rr_f"], p["tp_rr"], p["span"], p["wick"])
        # fair random at same prox/rr
        rnd = random_same_gate(p["prox_bps"], p["tp_rr"], p["span"], 0.15)
        if rnd.get("n"):
            eng_out = S.summarize(
                S.first_touch_levels(e, "1h")[e["epoch"][: len(S.first_touch_levels(e, "1h"))] >= S.SPLIT_EPOCH],
                "taker",
            )
            print(f"  MARGINAL LIFT (OOS net@taker): engulfing {eng_out['net']:+.1f} (n={eng_out['n']}) "
                  f"vs random {rnd['net']:+.1f} (n={rnd['n']}) -> lift {eng_out['net'] - rnd['net']:+.1f}")
        print("-" * 104)
