"""Shared analysis lib for tree-of-thoughts agents. Reads local cache /tmp/pq_cache (no DB).

Conventions:
- All returns in bps of entry notional. gross = before fees. net = gross - friction.
- Friction round-trip (bps): taker=10 (4.5x2 + slippage 0.5x2), maker=4 (2x2, limit no slip),
  maker_rebate=-2 (earn 1x2), zero=0. funding ~1 bps / 8h hold (assumption; BTC perp).
- Entries are dicts with numpy arrays: idx (bar index in its TF), price, islong (bool), epoch (int64 s).
- Positive edge means signed toward the trade direction.
"""
import bisect
import numpy as np

CACHE = "/tmp/pq_cache"
FR = {"taker": 10.0, "maker": 4.0, "maker_rebate": -2.0, "zero": 0.0}
FUNDING_PER_8H = 1.0  # bps per 8h held (assumption)
SPLIT_EPOCH = int(np.datetime64("2026-01-06", "s").astype("int64"))  # walk-forward boundary (~6/6)

_bars = {}
def load_bars(tf):
    if tf not in _bars:
        d = np.load(f"{CACHE}/bars_{tf}.npz")
        _bars[tf] = {k: d[k] for k in d.files}
    return _bars[tf]

def ema(arr, span):
    k = 2.0 / (span + 1.0); out = np.empty_like(arr, dtype=float); out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = k * arr[i] + (1 - k) * out[i - 1]
    return out

def atr(tf, period=14):
    b = load_bars(tf); H, L, C = b["h"], b["l"], b["c"]; n = len(H)
    TR = np.empty(n); TR[0] = H[0] - L[0]
    TR[1:] = np.maximum.reduce([H[1:] - L[1:], np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])])
    out = np.full(n, np.nan); cs = np.cumsum(TR); out[period:] = (cs[period:] - cs[:-period]) / period
    return out

def trend_up(tf, span=20):
    b = load_bars(tf); return b["c"] > ema(b["c"], span)

def trend_up_at(tf, epoch, span=20):
    """Trend of last COMPLETED bar on tf at/just before epoch. Returns bool or None."""
    b = load_bars(tf); ts = b["ts"]
    if not hasattr(trend_up_at, "_cache"): trend_up_at._cache = {}
    key = (tf, span)
    if key not in trend_up_at._cache: trend_up_at._cache[key] = trend_up(tf, span)
    up = trend_up_at._cache[key]
    k = bisect.bisect_right(ts, epoch) - 1
    return bool(up[k]) if k >= 0 else None

def idx_at(tf, epoch):
    """Index of bar whose ts == epoch (exact), else -1."""
    ts = load_bars(tf)["ts"]; k = bisect.bisect_left(ts, epoch)
    return k if k < len(ts) and ts[k] == epoch else -1

def detect_engulfing(tf, wick_pct=None, min_body_atr=None):
    """Simple engulfing on tf. Bull: prev bearish, cur bullish, cur body engulfs prev body.
    Entry at close of engulfing bar. Returns entries dict (idx, price, islong, epoch).
    Approximation of engulfing_pullback30_touch (no deferred pullback); note in reports."""
    b = load_bars(tf); O, H, L, C, ts = b["o"], b["h"], b["l"], b["c"], b["ts"]; n = len(O)
    A = atr(tf) if min_body_atr else None
    idx, price, islong, epoch = [], [], [], []
    for k in range(1, n):
        prev_bear = C[k-1] < O[k-1]; prev_bull = C[k-1] > O[k-1]
        cur_bull = C[k] > O[k]; cur_bear = C[k] < O[k]
        body = abs(C[k] - O[k])
        if min_body_atr and (A[k] is np.nan or body < min_body_atr * A[k]): continue
        if wick_pct is not None:
            rng = H[k] - L[k]
            if rng <= 0: continue
            up_wick = H[k] - max(O[k], C[k]); dn_wick = min(O[k], C[k]) - L[k]
        bull = prev_bear and cur_bull and O[k] <= C[k-1] and C[k] >= O[k-1]
        bear = prev_bull and cur_bear and O[k] >= C[k-1] and C[k] <= O[k-1]
        if bull and wick_pct is not None and up_wick > wick_pct * rng: bull = False
        if bear and wick_pct is not None and dn_wick > wick_pct * rng: bear = False
        if bull or bear:
            idx.append(k); price.append(C[k]); islong.append(bull); epoch.append(int(ts[k]))
    return dict(idx=np.array(idx), price=np.array(price), islong=np.array(islong, dtype=bool), epoch=np.array(epoch, dtype="int64"))

def load_real_entries():
    """The 8629 real engulfing_pullback30_touch 1m entries. idx maps into 1m bars."""
    d = np.load(f"{CACHE}/entries.npz"); ts1 = load_bars("1m")["ts"]
    idx = np.searchsorted(ts1, d["ets"])
    ok = (idx < len(ts1)) & (ts1[np.clip(idx, 0, len(ts1)-1)] == d["ets"])
    return dict(idx=idx[ok], price=d["ep"][ok], islong=d["islong"][ok], epoch=d["ets"][ok],
                sl=d["sl"][ok], tp=d["tp"][ok], qty=d["qty"][ok], pnl=d["pnl"][ok], comm=d["comm"][ok])

def _mask(entries, mask):
    return {k: (v[mask] if isinstance(v, np.ndarray) and len(v) == len(mask) else v) for k, v in entries.items()}

def filter_entries(entries, mask):
    return _mask(entries, mask)

def first_touch(entries, tf, sl_bps=None, tp_bps=None, sl_atr=None, tp_atr=None, sl_R=None, maxbars=240, tie="SL"):
    """First-touch exit sim on tf. Provide SL via sl_bps OR sl_atr(xATR). TP via tp_bps OR tp_atr OR sl_R(xSL).
    Returns gross bps array per trade. tie='SL' pessimistic."""
    b = load_bars(tf); H, L, C = b["h"], b["l"], b["c"]; n = len(H)
    A = atr(tf) if (sl_atr or tp_atr) else None
    out = []
    for j in range(len(entries["idx"])):
        i = int(entries["idx"][j]); ep = entries["price"][j]; isl = bool(entries["islong"][j])
        if i + 1 >= n: continue
        if sl_atr is not None:
            a = A[i]
            if not np.isfinite(a): continue
            sld = a * sl_atr
        else:
            sld = ep * sl_bps / 1e4
        if tp_atr is not None: tpd = A[i] * tp_atr
        elif sl_R is not None: tpd = sld * sl_R
        else: tpd = ep * tp_bps / 1e4
        j0, j1 = i + 1, min(i + 1 + maxbars, n); hh = H[j0:j1]; ll = L[j0:j1]
        if isl:
            sh = np.where(ll <= ep - sld)[0]; th = np.where(hh >= ep + tpd)[0]
        else:
            sh = np.where(hh >= ep + sld)[0]; th = np.where(ll <= ep - tpd)[0]
        si = sh[0] if len(sh) else 10**9; ti = th[0] if len(th) else 10**9
        if si == 10**9 and ti == 10**9:
            last = C[j1 - 1]; move = (last - ep) if isl else (ep - last); out.append(move / ep * 1e4)
        elif si <= ti: out.append(-sld / ep * 1e4)
        else: out.append(tpd / ep * 1e4)
    return np.array(out)

def fixed_horizon(entries, tf, hbars):
    """Signed gross bps if exit exactly hbars later (time-based / cross-TF hold proxy)."""
    b = load_bars(tf); C = b["c"]; n = len(C); out = []
    for j in range(len(entries["idx"])):
        i = int(entries["idx"][j]); ep = entries["price"][j]; sgn = 1 if entries["islong"][j] else -1
        if i + hbars < n: out.append(sgn * (C[i + hbars] - ep) / ep * 1e4)
    return np.array(out)

def in_out_masks(entries):
    e = entries["epoch"]; return e < SPLIT_EPOCH, e >= SPLIT_EPOCH

def summarize(bps, friction="maker", hold_hours=None, label=""):
    bps = np.asarray(bps); n = len(bps)
    if n == 0: return dict(label=label, n=0)
    g = float(bps.mean()); fr = FR[friction] if isinstance(friction, str) else float(friction)
    fund = (np.ceil(hold_hours / 8.0) * FUNDING_PER_8H) if hold_hours else 0.0
    net = g - fr - fund
    return dict(label=label, n=n, wr=float((bps > 0).mean()), gross=round(g, 3),
                friction=fr + fund, net=round(net, 3), edge_to_cost=round(g / (fr + fund), 2) if (fr + fund) else float("inf"),
                total_net_bps=round(net * n, 0))

def show(d):
    if d.get("n", 0) == 0: print(f"{d.get('label',''):30} n=0"); return
    print(f"{d['label']:30} n={d['n']:5} wr={d['wr']:.2f} gross={d['gross']:+6.2f} "
          f"fric={d['friction']:5.1f} net={d['net']:+6.2f} e/c={d['edge_to_cost']:+.2f} totnet={d['total_net_bps']:+.0f}bps")
