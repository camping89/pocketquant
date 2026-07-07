"""Find best ATR weights for SL/TP on 1m BTC using real engulfing entries + first-touch sim."""
import time
from datetime import datetime
import numpy as np
from pymongo import MongoClient, ASCENDING

URL = "mongodb://pocketquant:***REMOVED***@207.148.79.60:52017/pocketquant?authSource=admin"
c = MongoClient(URL, serverSelectionTimeoutMS=15000)
db = c["pocketquant"]
RUN = "019f36d2-5f4f-75cc-95c6-49a7496c3a86"

def pdt(s):
    return datetime.fromisoformat(str(s))

t0 = time.time()
# 1) load 1m bars in the run window
lo, hi = datetime(2025, 7, 1), datetime(2026, 7, 8)
cur = db["bars"].find(
    {"symbol": "BTCUSDT:BINANCE", "interval": "1m", "datetime": {"$gte": lo, "$lt": hi}},
    {"datetime": 1, "open": 1, "high": 1, "low": 1, "close": 1, "_id": 0},
).sort("datetime", ASCENDING)
bars = list(cur)
print(f"bars loaded: {len(bars)}  ({time.time()-t0:.1f}s)")
dt = [b["datetime"] for b in bars]
H = np.array([b["high"] for b in bars], dtype=float)
L = np.array([b["low"] for b in bars], dtype=float)
Cl = np.array([b["close"] for b in bars], dtype=float)
idx_of = {d: i for i, d in enumerate(dt)}

# 2) ATR(14) via Wilder-ish simple mean of true range
P = 14
TR = np.empty(len(bars))
TR[0] = H[0] - L[0]
TR[1:] = np.maximum.reduce([H[1:] - L[1:], np.abs(H[1:] - Cl[:-1]), np.abs(L[1:] - Cl[:-1])])
ATR = np.full(len(bars), np.nan)
csum = np.cumsum(TR)
ATR[P:] = (csum[P:] - csum[:-P]) / P  # trailing P-bar mean TR (excludes current bar)

# 3) load entries
trades = list(db["backtest_trades"].find(
    {"run_id": RUN}, {"entry_time": 1, "entry_price": 1, "direction": 1, "_id": 0}))
print(f"entries: {len(trades)}")

MAXBARS = 240
entries = []  # (idx, entry_price, is_long, atr_e)
miss = 0
for t in trades:
    d = pdt(t["entry_time"])
    i = idx_of.get(d)
    if i is None or i + 1 >= len(bars) or np.isnan(ATR[i]):
        miss += 1
        continue
    entries.append((i, float(t["entry_price"]), t["direction"] == "LONG", ATR[i]))
print(f"mapped entries: {len(entries)}  (missed {miss})")

# 4) MAE/MFE in ATR units (fixed window), for intuition
mae_atr, mfe_atr = [], []
for i, ep, isl, atr in entries[:6000]:
    j0, j1 = i + 1, min(i + 1 + MAXBARS, len(bars))
    hh = H[j0:j1]; ll = L[j0:j1]
    if isl:
        mfe = (hh.max() - ep) / atr; mae = (ep - ll.min()) / atr
    else:
        mfe = (ep - ll.min()) / atr; mae = (hh.max() - ep) / atr
    mfe_atr.append(mfe); mae_atr.append(mae)
mae_atr = np.array(mae_atr); mfe_atr = np.array(mfe_atr)
print(f"\n== MAE / MFE over {MAXBARS} bars, in ATR units (n={len(mae_atr)}) ==")
for label, arr in [("MAE (against)", mae_atr), ("MFE (favorable)", mfe_atr)]:
    print(f"{label:16} p25={np.percentile(arr,25):.1f}  median={np.median(arr):.1f}  p75={np.percentile(arr,75):.1f}  p90={np.percentile(arr,90):.1f}  ATR")


def simulate(sl_w, tp_dist_fn, min_atr_bps=0.0):
    """first-touch sim across entries. tp_dist_fn(sl_dist, atr)->tp_dist. returns stats."""
    Rs = []      # gross R per trade
    bps = []     # gross bps per trade (of entry)
    for i, ep, isl, atr in entries:
        if atr / ep * 10000 < min_atr_bps:
            continue
        sl_dist = atr * sl_w
        tp_dist = tp_dist_fn(sl_dist, atr)
        j0, j1 = i + 1, min(i + 1 + MAXBARS, len(bars))
        hh = H[j0:j1]; ll = L[j0:j1]
        if isl:
            sl_p = ep - sl_dist; tp_p = ep + tp_dist
            sl_hits = np.where(ll <= sl_p)[0]
            tp_hits = np.where(hh >= tp_p)[0]
        else:
            sl_p = ep + sl_dist; tp_p = ep - tp_dist
            sl_hits = np.where(hh >= sl_p)[0]
            tp_hits = np.where(ll <= tp_p)[0]
        si = sl_hits[0] if len(sl_hits) else 10**9
        ti = tp_hits[0] if len(tp_hits) else 10**9
        if si == 10**9 and ti == 10**9:
            # time stop at last close
            last = Cl[j1 - 1]
            move = (last - ep) if isl else (ep - last)
            r = move / sl_dist; b = move / ep * 10000
        elif si <= ti:  # tie -> SL (pessimistic)
            r = -1.0; b = -sl_dist / ep * 10000
        else:
            r = tp_dist / sl_dist; b = tp_dist / ep * 10000
        Rs.append(r); bps.append(b)
    Rs = np.array(Rs); bps = np.array(bps)
    n = len(Rs)
    if n == 0:
        return None
    return dict(n=n, wr=float((Rs > 0).mean()), avgR=float(Rs.mean()),
               avg_bps=float(bps.mean()), tot_bps=float(bps.sum()))

# 5) grid sweep
SL_W = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
TP_W = [3.0, 5.0, 7.0, 10.0, 14.0]     # mode A: TP = ATR * w
R_MULT = [1.5, 2.0, 3.0]               # mode B: TP = SL_dist * R
FR_MAKER = 4.0   # 2bps/side * 2 (limit both legs, optimistic)
FR_TAKER = 11.0  # ~4.5bps*2 + slippage ~2

rows = []
for slw in SL_W:
    for twp in TP_W:
        s = simulate(slw, lambda sld, atr, w=twp: atr * w)
        if s:
            rows.append(("A tp=%.0fxATR" % twp, slw, twp, s))
    for r in R_MULT:
        s = simulate(slw, lambda sld, atr, rr=r: sld * rr)
        if s:
            rows.append(("B tp=%.1fR" % r, slw, r, s))

def net_bps(s, fr):
    return s["avg_bps"] - fr

print(f"\n== grid (n≈{len(entries)} entries, friction maker={FR_MAKER}bps taker={FR_TAKER}bps rt) ==")
print(f"{'mode':11} {'slW':>4} {'n':>5} {'wr':>5} {'avgR':>6} {'gross_bps':>9} {'net@mk':>7} {'e/c@mk':>6} {'net@tk':>7}")
# sort by net@maker avg_bps
rows.sort(key=lambda x: net_bps(x[3], FR_MAKER), reverse=True)
for mode, slw, tp, s in rows[:14]:
    nm = net_bps(s, FR_MAKER); nt = net_bps(s, FR_TAKER)
    ec = s["avg_bps"] / FR_MAKER
    print(f"{mode:11} {slw:>4} {s['n']:>5} {s['wr']:>5.2f} {s['avgR']:>6.2f} {s['avg_bps']:>9.2f} {nm:>7.2f} {ec:>6.2f} {nt:>7.2f}")

print("\n== worst 3 (for contrast) ==")
for mode, slw, tp, s in rows[-3:]:
    nm = net_bps(s, FR_MAKER)
    print(f"{mode:11} {slw:>4} {s['n']:>5} {s['wr']:>5.2f} {s['avgR']:>6.2f} {s['avg_bps']:>9.2f} {nm:>7.2f}")

# 6) best cell + min_atr filter effect
best = rows[0]
print(f"\n== best cell {best[0]} slW={best[1]} + volatility floor filter ==")
for maf in (0.0, 3.0, 5.0, 8.0):
    if best[0].startswith("A"):
        s = simulate(best[1], lambda sld, atr, w=best[2]: atr * w, min_atr_bps=maf)
    else:
        s = simulate(best[1], lambda sld, atr, rr=best[2]: sld * rr, min_atr_bps=maf)
    nm = net_bps(s, FR_MAKER)
    print(f"min_atr>={maf:>4}bps  n={s['n']:>5} ({s['n']/len(entries)*100:4.1f}% kept)  wr={s['wr']:.2f}  gross_bps={s['avg_bps']:.2f}  net@mk={nm:+.2f}  total_net@mk={s['n']*nm:+.0f}bps")
print(f"\ntotal time {time.time()-t0:.1f}s")
