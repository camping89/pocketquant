"""Structure-level engulfing lib: swing S/R + structure-filtered entries + RR-aware exits.

New angle vs the 260706 research (which used only EMA trend filter + ATR):
engulfing is a TRIGGER; entries are gated by proximity to a higher-TF key
structure level (swing S/R), TP is the next opposing level (RR-aware), SL sits
beyond the level being defended. Cost bar = TAKER (~10 bps round-trip).

No-lookahead discipline (both are leaks if violated):
- Swing pivots need k bars AFTER to confirm -> a level is only "known" at
  ts[pivot_idx + k], never at the pivot bar itself. `levels_before(epoch)`
  filters on that confirm-epoch.
- Higher-TF trend uses the last bar CLOSED strictly before entry (bisect_right-1).

All returns in bps of entry notional. gross = before fees; net = gross - friction.
Friction round-trip (bps): taker=10 (4.5x2 comm + 0.5x2 slippage), maker=4, zero=0.
Reads /tmp/pq_cache (run pq_prefetch.py first).
"""

from __future__ import annotations

import bisect
import os

import numpy as np

CACHE = os.environ.get("PQ_CACHE", "/tmp/pq_cache")
FR = {"taker": 10.0, "maker": 4.0, "maker_rebate": -2.0, "zero": 0.0}
SPLIT_EPOCH = int(np.datetime64("2026-01-06", "s").astype("int64"))  # walk-forward boundary

_bars: dict[str, dict] = {}


def use_cache(path: str) -> None:
    """Point at a different per-symbol cache dir and drop all memoized state.
    Lets one process validate BTC/ETH/SOL sequentially without cross-contamination."""
    global CACHE
    CACHE = path
    _bars.clear()
    _trend_cache.clear()
    _levels_cache.clear()


def load_bars(tf: str) -> dict:
    if tf not in _bars:
        d = np.load(f"{CACHE}/bars_{tf}.npz")
        _bars[tf] = {k: d[k] for k in d.files}
    return _bars[tf]


def ema(arr: np.ndarray, span: int) -> np.ndarray:
    k = 2.0 / (span + 1.0)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = k * arr[i] + (1 - k) * out[i - 1]
    return out


def atr(tf: str, period: int = 14) -> np.ndarray:
    b = load_bars(tf)
    H, L, C = b["h"], b["l"], b["c"]
    n = len(H)
    TR = np.empty(n)
    TR[0] = H[0] - L[0]
    TR[1:] = np.maximum.reduce(
        [H[1:] - L[1:], np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])]
    )
    out = np.full(n, np.nan)
    cs = np.cumsum(TR)
    out[period:] = (cs[period:] - cs[:-period]) / period
    return out


_trend_cache: dict = {}


def trend_up_at(tf: str, epoch: int, span: int = 20) -> bool | None:
    """Trend of last COMPLETED bar on tf at/just before epoch (close > EMA span)."""
    b = load_bars(tf)
    ts = b["ts"]
    key = (tf, span)
    if key not in _trend_cache:
        _trend_cache[key] = b["c"] > ema(b["c"], span)
    up = _trend_cache[key]
    k = bisect.bisect_right(ts, epoch) - 1
    return bool(up[k]) if k >= 0 else None


# --------------------------------------------------------------------------
# Swing structure levels
# --------------------------------------------------------------------------
_levels_cache: dict = {}


def swing_levels(tf: str, k: int = 3):
    """Confirmed swing pivots on tf. A pivot high at i needs H[i] strictly the
    max of H[i-k .. i+k]; confirmed only at ts[i+k]. Returns two sorted-by-epoch
    lists: highs, lows -> each a tuple (confirm_epochs, prices) as np arrays.

    Sorted by confirm epoch so `levels_before` can bisect.
    """
    key = (tf, k)
    if key in _levels_cache:
        return _levels_cache[key]
    b = load_bars(tf)
    H, L, ts = b["h"], b["l"], b["ts"]
    n = len(H)
    hi_ep, hi_px, lo_ep, lo_px = [], [], [], []
    for i in range(k, n - k):
        wH = H[i - k : i + k + 1]
        wL = L[i - k : i + k + 1]
        if H[i] == wH.max() and (wH == H[i]).sum() == 1:
            hi_ep.append(int(ts[i + k]))
            hi_px.append(float(H[i]))
        if L[i] == wL.min() and (wL == L[i]).sum() == 1:
            lo_ep.append(int(ts[i + k]))
            lo_px.append(float(L[i]))
    res = (
        (np.array(hi_ep, dtype="int64"), np.array(hi_px)),
        (np.array(lo_ep, dtype="int64"), np.array(lo_px)),
    )
    _levels_cache[key] = res
    return res


def levels_before(tf: str, epoch: int, k: int = 3, lookback: int = 400):
    """All confirmed highs/lows known strictly before `epoch`, most recent
    `lookback` of each. Returns (highs_px, lows_px) as float arrays."""
    (hi_ep, hi_px), (lo_ep, lo_px) = swing_levels(tf, k)
    hi_n = bisect.bisect_left(hi_ep, epoch)
    lo_n = bisect.bisect_left(lo_ep, epoch)
    hp = hi_px[max(0, hi_n - lookback) : hi_n]
    lp = lo_px[max(0, lo_n - lookback) : lo_n]
    return hp, lp


def nearest_support(levels_low: np.ndarray, levels_high: np.ndarray, price: float):
    """Nearest level BELOW price (support). Consider both swing highs and lows
    (a broken resistance becomes support). Returns price or None."""
    alllv = np.concatenate([levels_low, levels_high]) if len(levels_high) else levels_low
    below = alllv[alllv < price]
    return float(below.max()) if len(below) else None


def nearest_resistance(levels_low: np.ndarray, levels_high: np.ndarray, price: float):
    alllv = np.concatenate([levels_low, levels_high]) if len(levels_high) else levels_low
    above = alllv[alllv > price]
    return float(above.min()) if len(above) else None


# --------------------------------------------------------------------------
# Engulfing trigger on a TF
# --------------------------------------------------------------------------
def detect_engulfing(tf: str, wick_pct: float | None = None):
    """Full-candle engulfing on tf (body+range engulf, matches core detector).
    Entry at close of the engulfing bar. Optional rejection-wick quality filter.
    Returns entries dict (idx, price, islong, epoch)."""
    b = load_bars(tf)
    O, H, L, C, ts = b["o"], b["h"], b["l"], b["c"], b["ts"]
    n = len(O)
    idx, price, islong, epoch = [], [], [], []
    for i in range(1, n):
        prev_bear = C[i - 1] < O[i - 1]
        prev_bull = C[i - 1] > O[i - 1]
        cur_bull = C[i] > O[i]
        cur_bear = C[i] < O[i]
        bull = (
            prev_bear and cur_bull
            and O[i] <= C[i - 1] and C[i] >= O[i - 1]
            and H[i] >= H[i - 1] and L[i] <= L[i - 1]
        )
        bear = (
            prev_bull and cur_bear
            and O[i] >= C[i - 1] and C[i] <= O[i - 1]
            and H[i] >= H[i - 1] and L[i] <= L[i - 1]
        )
        if not (bull or bear):
            continue
        if wick_pct is not None:
            rng = H[i] - L[i]
            if rng <= 0:
                continue
            if bull and (H[i] - C[i]) / rng > wick_pct:
                continue
            if bear and (C[i] - L[i]) / rng > wick_pct:
                continue
        idx.append(i)
        price.append(float(C[i]))
        islong.append(bull)
        epoch.append(int(ts[i]))
    return dict(
        idx=np.array(idx),
        price=np.array(price),
        islong=np.array(islong, dtype=bool),
        epoch=np.array(epoch, dtype="int64"),
    )


# --------------------------------------------------------------------------
# Structure-gated entry builder
# --------------------------------------------------------------------------
def build_structure_entries(
    tf: str,
    struct_tf: str,
    *,
    wick_pct: float | None = 0.4,
    prox_bps: float = 15.0,
    pivot_k: int = 3,
    sl_buffer_bps: float = 5.0,
    min_rr: float = 1.5,
    trend_tf: str | None = None,
    trend_span: int = 20,
    require_aligned: bool = True,
    tp_rr: float | None = None,
):
    """Engulfing on `tf`, gated by proximity to a `struct_tf` swing level, with
    RR-aware TP = next opposing level. Returns entries dict with per-trade
    sl/tp/rr arrays ready for first_touch_levels.

    LONG: bullish engulfing whose low is within prox_bps of a support; TP =
    nearest resistance above entry; SL = support*(1 - buffer). SHORT mirrors.
    Optional higher-TF trend alignment gate.

    tp_mode: TP = next opposing level (default). If `tp_rr` set, TP = entry +/-
    tp_rr*risk instead (fixed-RR target; the level is still required to exist as
    a gate, so both mechanisms share the same entry population).
    """
    eng = detect_engulfing(tf, wick_pct=wick_pct)
    b = load_bars(tf)
    Ltf = b["l"]
    Htf = b["h"]
    idxs, prices, islongs, epochs, sls, tps, rrs = [], [], [], [], [], [], []
    for j in range(len(eng["idx"])):
        i = int(eng["idx"][j])
        ep = float(eng["price"][j])
        isl = bool(eng["islong"][j])
        e = int(eng["epoch"][j])
        hp, lp = levels_before(struct_tf, e, k=pivot_k)
        if len(lp) == 0 and len(hp) == 0:
            continue
        if trend_tf is not None:
            up = trend_up_at(trend_tf, e, span=trend_span)
            if up is None:
                continue
            aligned = (isl and up) or ((not isl) and (not up))
            if require_aligned and not aligned:
                continue
        if isl:
            sup = nearest_support(lp, hp, ep)
            res = nearest_resistance(lp, hp, ep)
            if sup is None or res is None:
                continue
            # proximity: the bar's low must have tagged near support
            bar_low = float(Ltf[i])
            dist_bps = (bar_low - sup) / ep * 1e4
            if not (-prox_bps <= dist_bps <= prox_bps):
                continue
            sl = sup * (1 - sl_buffer_bps / 1e4)
            if sl >= ep:
                continue
            tp = ep + tp_rr * (ep - sl) if tp_rr is not None else res
            if tp <= ep:
                continue
            rr = (tp - ep) / (ep - sl)
        else:
            sup = nearest_support(lp, hp, ep)
            res = nearest_resistance(lp, hp, ep)
            if sup is None or res is None:
                continue
            bar_high = float(Htf[i])
            dist_bps = (res - bar_high) / ep * 1e4
            if not (-prox_bps <= dist_bps <= prox_bps):
                continue
            sl = res * (1 + sl_buffer_bps / 1e4)
            if sl <= ep:
                continue
            tp = ep - tp_rr * (sl - ep) if tp_rr is not None else sup
            if tp >= ep:
                continue
            rr = (ep - tp) / (sl - ep)
        if rr < min_rr:
            continue
        idxs.append(i)
        prices.append(ep)
        islongs.append(isl)
        epochs.append(e)
        sls.append(sl)
        tps.append(tp)
        rrs.append(rr)
    return dict(
        idx=np.array(idxs),
        price=np.array(prices),
        islong=np.array(islongs, dtype=bool),
        epoch=np.array(epochs, dtype="int64"),
        sl=np.array(sls),
        tp=np.array(tps),
        rr=np.array(rrs),
    )


def first_touch_levels(
    entries: dict, tf: str, maxbars: int = 480, tie: str = "SL", with_exits: bool = False
):
    """Path-aware first-touch with per-trade SL/TP prices. Returns gross bps
    per trade (signed toward trade direction). tie='SL' pessimistic (both hit in
    one bar -> SL). Unresolved after maxbars -> mark-to-close.

    If with_exits, also returns a parallel int array: 0=SL, 1=TP, 2=mark-close."""
    b = load_bars(tf)
    H, L, C = b["h"], b["l"], b["c"]
    n = len(H)
    out, kind = [], []
    for j in range(len(entries["idx"])):
        i = int(entries["idx"][j])
        ep = float(entries["price"][j])
        isl = bool(entries["islong"][j])
        sl = float(entries["sl"][j])
        tp = float(entries["tp"][j])
        if i + 1 >= n:
            continue
        j0, j1 = i + 1, min(i + 1 + maxbars, n)
        hh = H[j0:j1]
        ll = L[j0:j1]
        if isl:
            sh = np.where(ll <= sl)[0]
            th = np.where(hh >= tp)[0]
        else:
            sh = np.where(hh >= sl)[0]
            th = np.where(ll <= tp)[0]
        si = sh[0] if len(sh) else 10**9
        ti = th[0] if len(th) else 10**9
        if si == 10**9 and ti == 10**9:
            last = C[j1 - 1]
            move = (last - ep) if isl else (ep - last)
            out.append(move / ep * 1e4)
            kind.append(2)
        elif si < ti or (si == ti and tie == "SL"):
            move = (sl - ep) if isl else (ep - sl)
            out.append(move / ep * 1e4)
            kind.append(0)
        else:
            move = (tp - ep) if isl else (ep - tp)
            out.append(move / ep * 1e4)
            kind.append(1)
    if with_exits:
        return np.array(out), np.array(kind)
    return np.array(out)


def in_out_masks(entries: dict):
    e = entries["epoch"]
    return e < SPLIT_EPOCH, e >= SPLIT_EPOCH


def summarize(bps: np.ndarray, friction="taker", label: str = "") -> dict:
    bps = np.asarray(bps)
    n = len(bps)
    if n == 0:
        return dict(label=label, n=0)
    g = float(bps.mean())
    fr = FR[friction] if isinstance(friction, str) else float(friction)
    net = g - fr
    return dict(
        label=label, n=n, wr=float((bps > 0).mean()), gross=round(g, 2),
        friction=fr, net=round(net, 2),
        edge_to_cost=round(g / fr, 2) if fr else float("inf"),
        total_net_bps=round(net * n, 0),
    )


def show(d: dict) -> None:
    if d.get("n", 0) == 0:
        print(f"{d.get('label', ''):42} n=0")
        return
    print(
        f"{d['label']:42} n={d['n']:5} wr={d['wr']:.2f} gross={d['gross']:+6.2f} "
        f"fric={d['friction']:4.1f} net={d['net']:+7.2f} e/c={d['edge_to_cost']:+5.2f} "
        f"totnet={d['total_net_bps']:+.0f}"
    )
