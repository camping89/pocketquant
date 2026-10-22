"""Stability surface around the one viable mechanism (1h engulfing, 1d structure
gate, 1d trend gate, fixed-RR exit). If OOS net@taker is positive across a
contiguous plateau of (rr x prox x trend_span), the edge is a region not a point
-> not curve-fit. Also a random-entry control: same trend+level gate, random
qualifying bar instead of engulfing, to test engulfing's marginal contribution.
"""

from __future__ import annotations

import numpy as np

import pq_structure_lib as S


def oos_net(tf, struct_tf, trend_tf, prox, rr_filter, tp_rr, span, wick):
    e = S.build_structure_entries(
        tf=tf, struct_tf=struct_tf, trend_tf=trend_tf, prox_bps=prox,
        min_rr=rr_filter, wick_pct=wick, trend_span=span, tp_rr=tp_rr,
    )
    if len(e["idx"]) < 8:
        return None
    bps = S.first_touch_levels(e, tf)
    ep = e["epoch"][: len(bps)]
    din = S.summarize(bps[ep < S.SPLIT_EPOCH], "taker")
    dout = S.summarize(bps[ep >= S.SPLIT_EPOCH], "taker")
    return din, dout


if __name__ == "__main__":
    print("=" * 100)
    print("STABILITY SURFACE — OOS net@taker across param region (1h->1d, 1d trend, fixed-RR)")
    print("cells show:  OUT_net(n_out) | IN_net   — positive-both marked *")
    print("=" * 100)
    header = "rr\\prox    " + "".join(f"{p:>16}" for p in (60, 80, 100, 120))
    for tp_rr in (2.0, 2.5, 3.0, 3.5, 4.0):
        row = [f"rr={tp_rr:<7}"]
        for prox in (60, 80, 100, 120):
            r = oos_net("1h", "1d", "1d", prox, 1.3, tp_rr, 20, 0.6)
            if r is None:
                row.append(f"{'--':>16}")
                continue
            din, dout = r
            star = "*" if din.get("net", -9) > 0 and dout.get("net", -9) > 0 else " "
            row.append(f"{dout['net']:+6.1f}({dout['n']:3}){star}{din['net']:+5.0f}"[:16].rjust(16))
        print("".join(row))
    print("=" * 100)
    print("Trend-span robustness (prox=100, rr=3.0):")
    for span in (10, 20, 50, 100):
        r = oos_net("1h", "1d", "1d", 100, 1.3, 3.0, span, 0.6)
        if r:
            din, dout = r
            print(f"  span={span:4}  IN net={din['net']:+6.1f} (n={din['n']})   OUT net={dout['net']:+6.1f} (n={dout['n']})")
    print("=" * 100)
    print("RANDOM-ENTRY CONTROL — same trend+1d-level gate, random qualifying 1h bar (no engulfing):")
    print("(if random matches engulfing, the engulfing trigger adds nothing — edge is trend+level)")
    # emulate: take ALL 1h bars aligned with 1d trend and near a 1d level, random SL/TP by rr
    b = S.load_bars("1h")
    O, H, L, C, ts = b["o"], b["h"], b["l"], b["c"], b["ts"]
    rng = np.random.default_rng(42)
    for tp_rr in (3.0,):
        idxs, prices, islongs, epochs, sls, tps = [], [], [], [], [], []
        for i in range(1, len(C)):
            e = int(ts[i])
            up = S.trend_up_at("1d", e, span=20)
            if up is None:
                continue
            if rng.random() > 0.15:  # subsample to match engulfing count scale
                continue
            ep = float(C[i])
            hp, lp = S.levels_before("1d", e, k=3)
            if len(lp) == 0 and len(hp) == 0:
                continue
            isl = bool(up)
            if isl:
                sup = S.nearest_support(lp, hp, ep)
                if sup is None:
                    continue
                bl = float(L[i])
                if not (-100 <= (bl - sup) / ep * 1e4 <= 100):
                    continue
                sl = sup * (1 - 5 / 1e4)
                if sl >= ep:
                    continue
                tp = ep + tp_rr * (ep - sl)
            else:
                res = S.nearest_resistance(lp, hp, ep)
                if res is None:
                    continue
                bh = float(H[i])
                if not (-100 <= (res - bh) / ep * 1e4 <= 100):
                    continue
                sl = res * (1 + 5 / 1e4)
                if sl <= ep:
                    continue
                tp = ep - tp_rr * (sl - ep)
            idxs.append(i); prices.append(ep); islongs.append(isl); epochs.append(e); sls.append(sl); tps.append(tp)
        ec = dict(idx=np.array(idxs), price=np.array(prices), islong=np.array(islongs, dtype=bool),
                  epoch=np.array(epochs, dtype="int64"), sl=np.array(sls), tp=np.array(tps))
        bps = S.first_touch_levels(ec, "1h")
        epx = ec["epoch"][: len(bps)]
        S.show(S.summarize(bps[epx < S.SPLIT_EPOCH], "taker", f"RANDOM rr={tp_rr} IN"))
        S.show(S.summarize(bps[epx >= S.SPLIT_EPOCH], "taker", f"RANDOM rr={tp_rr} OUT"))
