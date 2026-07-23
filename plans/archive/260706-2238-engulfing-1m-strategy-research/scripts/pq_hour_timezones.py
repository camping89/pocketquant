"""By-hour signed forward return (60m) across UTC / New York / Vietnam.

Reproduces the Phase-5 time-of-day finding but emits ALL 24 hours (not just
top/bottom) and shows the same bucket in three timezones.

Buckets are keyed by NEW YORK local hour (America/New_York, DST-aware) so each
row lines up with the US cash-equities session regardless of season. Because NY
observes DST, one NY local hour maps to two UTC hours across the year (NY+5 in
winter EST, NY+4 in summer EDT); UTC and VN (UTC+7, no DST) are therefore shown
as the set of clock hours the bucket's entries actually fell into.
"""
import os, time, bisect
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from pymongo import MongoClient, ASCENDING

URL = os.environ["MONGODB_URL"]  # do NOT hardcode; export MONGODB_URL from .env
db = MongoClient(URL, serverSelectionTimeoutMS=15000)["pocketquant"]
RUN = "019f36d2-5f4f-75cc-95c6-49a7496c3a86"

NY = ZoneInfo("America/New_York")
VN = ZoneInfo("Asia/Ho_Chi_Minh")  # UTC+7, no DST
UTC = ZoneInfo("UTC")

t0 = time.time()
lo, hi = datetime(2025, 7, 1), datetime(2026, 7, 8)
bars = list(db["bars"].find(
    {"symbol": "BTCUSDT:BINANCE", "interval": "1m", "datetime": {"$gte": lo, "$lt": hi}},
    {"datetime": 1, "close": 1, "_id": 0}).sort("datetime", ASCENDING))
dt = [b["datetime"] for b in bars]
Cl = np.array([b["close"] for b in bars])
idx_of = {d: i for i, d in enumerate(dt)}
n = len(bars)
print(f"1m bars {n} ({time.time()-t0:.1f}s)")

def ema(arr, span):
    a = 2/(span+1); out = np.empty_like(arr); out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = a*arr[i] + (1-a)*out[i-1]
    return out

# 1h trend via EMA20 on 1h closes
h1 = list(db["bars"].find({"symbol": "BTCUSDT:BINANCE", "interval": "1h", "datetime": {"$gte": datetime(2025,6,1), "$lt": hi}},
    {"datetime":1,"close":1,"_id":0}).sort("datetime", ASCENDING))
h1dt = [b["datetime"] for b in h1]; h1cl = np.array([b["close"] for b in h1])
h1up = h1cl > ema(h1cl, 20)
def htf_up(t):
    k = bisect.bisect_right(h1dt, t) - 1
    return bool(h1up[k]) if k >= 0 else None

trades = list(db["backtest_trades"].find({"run_id": RUN}, {"entry_time":1,"entry_price":1,"direction":1,"_id":0}))
H = 60
rec = []
for tr in trades:
    i = idx_of.get(tr["entry_time"])
    if i is None or i+H >= n:
        continue
    ep = tr["entry_price"]; isl = tr["direction"] == "LONG"; sgn = 1 if isl else -1
    fwd = sgn*(Cl[i+H]-ep)/ep*1e4
    up = htf_up(tr["entry_time"])
    t = dt[i]
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    rec.append(dict(ny_hour=t.astimezone(NY).hour, fwd=fwd,
                    aligned_1h=(up == isl) if up is not None else None,
                    utc_hour=t.astimezone(UTC).hour, vn_hour=t.astimezone(VN).hour))
print(f"entries: {len(rec)}")

def by_hour(subset, label):
    print(f"\n== {label}: signed fwd 60m by NEW YORK local hour (all 24) ==")
    print(f"  {'NY':>5} {'UTC':>10} {'VN':>10} {'bps':>8} {'n':>6}")
    rows = []
    for hh in range(24):
        sub = [r for r in subset if r["ny_hour"] == hh]
        if not sub:
            continue
        m = float(np.mean([r["fwd"] for r in sub]))
        # UTC / VN clock hour(s) this NY bucket's entries actually fell into
        utc = sorted({r["utc_hour"] for r in sub})
        vn = sorted({r["vn_hour"] for r in sub})
        utc_s = "/".join(f"{x:02d}:00" for x in utc)
        vn_s = "/".join(f"{x:02d}:00" for x in vn)
        rows.append((hh, utc_s, vn_s, m, len(sub)))
    for hh, utc_s, vn_s, m, cnt in rows:
        print(f"  {hh:02d}:00 {utc_s:>10} {vn_s:>10} {m:+8.2f} {cnt:>6}")
    return rows

by_hour(rec, "ALL entries")
by_hour([r for r in rec if r["aligned_1h"] is True], "1h-ALIGNED entries")

# sanity: NY 09:00 bucket should span the US cash-equities open (9:30 ET)
ny9 = [r for r in rec if r["ny_hour"] == 9]
print(f"\nNY 09:00 bucket: n={len(ny9)} utc={sorted({r['utc_hour'] for r in ny9})} "
      f"vn={sorted({r['vn_hour'] for r in ny9})}")
print(f"time {time.time()-t0:.1f}s")
