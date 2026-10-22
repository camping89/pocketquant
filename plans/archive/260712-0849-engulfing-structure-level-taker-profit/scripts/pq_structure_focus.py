"""Focused sweep on the viable high-TF zone: maximize OOS sample + prove edge
carrier via controls. Report exit mix (SL/TP/mark-close) and walk-forward net.

Controls per finalist:
- counter: require_aligned but flip alignment (counter-trend) -> should collapse.
- notrend: drop trend gate -> isolates trend filter's contribution.
The structure gate is always on; we vary what surrounds it.
"""

from __future__ import annotations

import numpy as np

import pq_structure_lib as S


def evaluate(label, tp_note="", **kw):
    e = S.build_structure_entries(**kw)
    if len(e["idx"]) < 8:
        print(f"{label:34} {tp_note:10} n={len(e['idx'])} (too few)")
        return None
    bps, kind = S.first_touch_levels(e, kw["tf"], with_exits=True)
    ep = e["epoch"][: len(bps)]
    oi = ep < S.SPLIT_EPOCH
    oo = ep >= S.SPLIT_EPOCH
    d_in = S.summarize(bps[oi], "taker", f"{label} {tp_note} IN")
    d_out = S.summarize(bps[oo], "taker", f"{label} {tp_note} OUT")
    S.show(d_in)
    S.show(d_out)
    mix = np.bincount(kind, minlength=3)
    print(
        f"{'   exits: SL/TP/markclose':34} = {mix[0]}/{mix[1]}/{mix[2]}  "
        f"| taker net both halves > 0 ? {'YES' if d_in.get('net',0) > 0 and d_out.get('net',0) > 0 else 'no'}"
    )
    return d_in, d_out


def controls(label, **kw):
    print(f"  -- controls for {label} --")
    # counter-trend
    kw_c = dict(kw)
    e = S.build_structure_entries(**kw)
    # flip trend requirement by inverting islong-vs-trend test: emulate via
    # require_aligned=True but swap by detecting on opposite alignment.
    # Simplest: run with require_aligned but keep counter set by post-filter.
    up_all = []
    for j in range(len(e["idx"])):
        up = S.trend_up_at(kw["trend_tf"], int(e["epoch"][j]), span=kw.get("trend_span", 20))
        isl = bool(e["islong"][j])
        up_all.append((isl and up) or ((not isl) and (not up)))
    # e is already aligned-only (require_aligned default True) so counter is empty here;
    # instead rebuild with a counter helper:
    ec = _counter_entries(**kw)
    if len(ec["idx"]) >= 8:
        bps = S.first_touch_levels(ec, kw["tf"])
        ep = ec["epoch"][: len(bps)]
        S.show(S.summarize(bps[ep < S.SPLIT_EPOCH], "taker", f"{label} COUNTER IN"))
        S.show(S.summarize(bps[ep >= S.SPLIT_EPOCH], "taker", f"{label} COUNTER OUT"))
    else:
        print(f"    counter n={len(ec['idx'])} (too few)")


def _counter_entries(**kw):
    """Same structure gate but keep only counter-trend entries."""
    kw2 = dict(kw)
    trend_tf = kw2.pop("trend_tf")
    span = kw2.pop("trend_span", 20)
    kw2["trend_tf"] = None  # disable internal gate; filter manually
    e = S.build_structure_entries(trend_tf=None, **{k: v for k, v in kw.items() if k not in ("trend_tf", "trend_span", "require_aligned")})
    keep = []
    for j in range(len(e["idx"])):
        up = S.trend_up_at(trend_tf, int(e["epoch"][j]), span=span)
        if up is None:
            continue
        isl = bool(e["islong"][j])
        aligned = (isl and up) or ((not isl) and (not up))
        keep.append(not aligned)  # counter only
    keep = np.array(keep, dtype=bool)
    return {k: (v[keep] if isinstance(v, np.ndarray) and len(v) == len(keep) else v) for k, v in e.items()}


FINALISTS = [
    # V1: level-target TP, 1d trend gate, 1h entry on 1d structure
    ("V1 1h->1d levelTP", "", dict(tf="1h", struct_tf="1d", trend_tf="1d", prox_bps=60, min_rr=1.5, wick_pct=0.5)),
    # V2: same gate, fixed-RR 3 exit (mechanism differs: momentum-run vs level-revert)
    ("V2 1h->1d rr3", "rr=3", dict(tf="1h", struct_tf="1d", trend_tf="1d", prox_bps=60, min_rr=1.5, wick_pct=0.5, tp_rr=3.0)),
    # V3: 4h structure on 1h entry, wider prox (different structure granularity)
    ("V3 1h->4h levelTP", "", dict(tf="1h", struct_tf="4h", trend_tf="1d", prox_bps=50, min_rr=1.5, wick_pct=0.5)),
    # extra: wider prox to grow OOS n
    ("X 1h->1d prox100", "", dict(tf="1h", struct_tf="1d", trend_tf="1d", prox_bps=100, min_rr=1.3, wick_pct=0.6)),
    ("X 1h->1d rr2 p80", "", dict(tf="1h", struct_tf="1d", trend_tf="1d", prox_bps=80, min_rr=1.5, wick_pct=0.6, tp_rr=2.0)),
]

if __name__ == "__main__":
    print("=" * 104)
    print("FOCUSED HIGH-TF STRUCTURE SWEEP — net@taker, split 2026-01-06, exit mix, controls")
    print("=" * 104)
    for label, note, kw in FINALISTS:
        r = evaluate(label, note, **kw)
        if r and kw.get("trend_tf"):
            controls(label, **kw)
        print("-" * 104)
