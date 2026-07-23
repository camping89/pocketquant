"""Screen entry filters: does any subset give positive signed forward return > friction?"""
import time, bisect
from datetime import datetime
import numpy as np
from pymongo import MongoClient, ASCENDING

import os; URL = os.environ["MONGODB_URL"]  # do NOT hardcode; export MONGODB_URL from .env
db = MongoClient(URL, serverSelectionTimeoutMS=15000)["pocketquant"]
RUN = "019f36d2-5f4f-75cc-95c6-49a7496c3a86"
FR = 4.0  # maker round-trip friction bps

t0 = time.time()
lo, hi = datetime(2025, 7, 1), datetime(2026, 7, 8)
bars = list(db["bars"].find(
    {"symbol": "BTCUSDT:BINANCE", "interval": "1m", "datetime": {"$gte": lo, "$lt": hi}},
    {"datetime": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "_id": 0}).sort("datetime", ASCENDING))
dt = [b["datetime"] for b in bars]
H = np.array([b["high"] for b in bars]); L = np.array([b["low"] for b in bars])
Cl = np.array([b["close"] for b in bars]); V = np.array([b.get("volume", 0.0) for b in bars])
idx_of = {d: i for i, d in enumerate(dt)}
n = len(bars)
print(f"1m bars {n} ({time.time()-t0:.1f}s)")

# ATR(14)
TR = np.empty(n); TR[0] = H[0]-L[0]
TR[1:] = np.maximum.reduce([H[1:]-L[1:], np.abs(H[1:]-Cl[:-1]), np.abs(L[1:]-Cl[:-1])])
ATR = np.full(n, np.nan); cs = np.cumsum(TR); ATR[14:] = (cs[14:]-cs[:-14])/14

# 1m EMA200 (long trend proxy ~3.3h)
def ema(arr, span):
    a = 2/(span+1); out = np.empty_like(arr); out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = a*arr[i] + (1-a)*out[i-1]
    return out
EMA200 = ema(Cl, 200)

# volume z (prior 60)
Vz = np.zeros(n)
for i in range(60, n):
    w = V[i-60:i]; m = w.mean(); s = w.std()
    Vz[i] = (V[i]-m)/s if s > 0 else 0.0

# 1h trend via EMA20 on 1h closes
h1 = list(db["bars"].find({"symbol": "BTCUSDT:BINANCE", "interval": "1h", "datetime": {"$gte": datetime(2025,6,1), "$lt": hi}},
    {"datetime":1,"close":1,"_id":0}).sort("datetime", ASCENDING))
h1dt = [b["datetime"] for b in h1]; h1cl = np.array([b["close"] for b in h1])
h1ema = ema(h1cl, 20)
h1up = h1cl > h1ema  # boolean per 1h bar
def htf_up(t):
    k = bisect.bisect_right(h1dt, t) - 1
    return bool(h1up[k]) if k >= 0 else None

# entries
trades = list(db["backtest_trades"].find({"run_id": RUN}, {"entry_time":1,"entry_price":1,"direction":1,"_id":0}))
HOR = [15, 30, 60, 120]
rec = []  # dict per entry
for tr in trades:
    i = idx_of.get(tr["entry_time"])
    if i is None or np.isnan(ATR[i]) or i+max(HOR) >= n:
        continue
    ep = tr["entry_price"]; isl = tr["direction"] == "LONG"; sgn = 1 if isl else -1
    fwd = {h: sgn*(Cl[i+h]-ep)/ep*1e4 for h in HOR}  # signed bps
    up = htf_up(tr["entry_time"])
    rec.append(dict(i=i, isl=isl, atr_bps=ATR[i]/ep*1e4, hour=dt[i].hour, vz=Vz[i],
                    m1_up=bool(Cl[i] > EMA200[i]), htf_up=up,
                    aligned_1h=(up == isl) if up is not None else None,
                    aligned_m1=(bool(Cl[i] > EMA200[i]) == isl), fwd=fwd))
print(f"entries screened: {len(rec)}")

def stat(sub, label):
    if len(sub) < 50:
        print(f"{label:34} n={len(sub):5}  (too few)"); return
    row = f"{label:34} n={len(sub):5}"
    for h in HOR:
        arr = np.array([r["fwd"][h] for r in sub])
        row += f" | {h:>3}m {arr.mean():+6.2f}"
    print(row)

print(f"\n== avg SIGNED forward return (bps) by subset; friction={FR}bps. Need >{FR} to exploit ==")
print(f"{'subset':34} {'':7}   " + "   ".join(f"{h}m" for h in HOR))
stat(rec, "ALL (baseline)")
stat([r for r in rec if r["aligned_1h"] is True], "1h-trend ALIGNED")
stat([r for r in rec if r["aligned_1h"] is False], "1h-trend COUNTER (fade htf)")
stat([r for r in rec if r["aligned_m1"]], "1m-EMA200 ALIGNED")
stat([r for r in rec if not r["aligned_m1"]], "1m-EMA200 COUNTER")
stat([r for r in rec if r["atr_bps"] >= 5], "ATR>=5bps (high vol)")
stat([r for r in rec if r["vz"] >= 1.0], "vol z>=1 (volume spike)")
stat([r for r in rec if r["vz"] >= 2.0], "vol z>=2 (big spike)")
# combos
stat([r for r in rec if r["aligned_1h"] is True and r["atr_bps"] >= 5], "1h-ALIGNED & ATR>=5")
stat([r for r in rec if r["aligned_1h"] is True and r["vz"] >= 1.0], "1h-ALIGNED & volz>=1")
stat([r for r in rec if r["aligned_m1"] and r["atr_bps"] >= 5], "1m-ALIGNED & ATR>=5")

# FADE: flip sign -> is reversed entry positive?
print(f"\n== FADE (reverse every entry) avg signed fwd return ==")
for h in HOR:
    arr = np.array([-r["fwd"][h] for r in rec])
    print(f"  fade {h:>3}m: {arr.mean():+.2f} bps")

# by hour (UTC) at 60m
print(f"\n== by hour UTC (60m signed fwd, bps) — top/bottom ==")
byh = []
for hh in range(24):
    sub = [r for r in rec if r["hour"] == hh]
    if len(sub) >= 100:
        byh.append((hh, np.mean([r["fwd"][60] for r in sub]), len(sub)))
byh.sort(key=lambda x: x[1], reverse=True)
for hh, m, cnt in byh[:4] + byh[-4:]:
    print(f"  {hh:02d}:00 UTC  {m:+6.2f} bps  n={cnt}")
print(f"\ntime {time.time()-t0:.1f}s")
