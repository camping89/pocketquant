"""Does edge keep growing if we hold longer (cross-timeframe exit)? Measure signed fwd return vs horizon."""
import time, bisect
from datetime import datetime
import numpy as np
from pymongo import MongoClient, ASCENDING

URL = "mongodb://pocketquant:***REMOVED***@207.148.79.60:52017/pocketquant?authSource=admin"
db = MongoClient(URL, serverSelectionTimeoutMS=15000)["pocketquant"]
RUN = "019f36d2-5f4f-75cc-95c6-49a7496c3a86"
FR_MK, FR_TK = 4.0, 11.0

t0 = time.time()
bars = list(db["bars"].find({"symbol":"BTCUSDT:BINANCE","interval":"1m","datetime":{"$gte":datetime(2025,7,1),"$lt":datetime(2026,7,8)}},
    {"datetime":1,"high":1,"low":1,"close":1,"_id":0}).sort("datetime",ASCENDING))
dt=[b["datetime"] for b in bars]; H=np.array([b["high"] for b in bars]); L=np.array([b["low"] for b in bars]); Cl=np.array([b["close"] for b in bars])
idx_of={d:i for i,d in enumerate(dt)}; n=len(bars)
TR=np.empty(n); TR[0]=H[0]-L[0]; TR[1:]=np.maximum.reduce([H[1:]-L[1:],np.abs(H[1:]-Cl[:-1]),np.abs(L[1:]-Cl[:-1])])
ATR=np.full(n,np.nan); cs=np.cumsum(TR); ATR[14:]=(cs[14:]-cs[:-14])/14

def ema(a,span):
    k=2/(span+1); o=np.empty_like(a); o[0]=a[0]
    for i in range(1,len(a)): o[i]=k*a[i]+(1-k)*o[i-1]
    return o
h1=list(db["bars"].find({"symbol":"BTCUSDT:BINANCE","interval":"1h","datetime":{"$gte":datetime(2025,6,1),"$lt":datetime(2026,7,8)}},
    {"datetime":1,"close":1,"_id":0}).sort("datetime",ASCENDING))
h1dt=[b["datetime"] for b in h1]; h1up=np.array([b["close"] for b in h1])>ema(np.array([b["close"] for b in h1]),20)
def htf_up(t):
    k=bisect.bisect_right(h1dt,t)-1
    return bool(h1up[k]) if k>=0 else None

trades=list(db["backtest_trades"].find({"run_id":RUN},{"entry_time":1,"entry_price":1,"direction":1,"_id":0}))
HOR=[30,60,120,240,480,960,1440,2880]  # minutes: 0.5h..48h
E=[]  # (i, ep, sgn, atr_bps, aligned)
for tr in trades:
    i=idx_of.get(tr["entry_time"])
    if i is None or np.isnan(ATR[i]): continue
    ep=tr["entry_price"]; isl=tr["direction"]=="LONG"; up=htf_up(tr["entry_time"])
    aligned=(up==isl) if up is not None else None
    E.append((i,ep,1 if isl else -1, ATR[i]/ep*1e4, aligned))
print(f"entries {len(E)}  time {time.time()-t0:.1f}s")

def curve(pred, label):
    sub=[e for e in E if pred(e)]
    print(f"\n== {label}  (n={len(sub)}) ==")
    print(f"{'hold':>7} {'gross':>7} {'net@mk':>7} {'net@tk':>7}  {'n_valid':>7}")
    for h in HOR:
        vals=[]
        for i,ep,sgn,atrb,al in sub:
            if i+h < n:
                vals.append(sgn*(Cl[i+h]-ep)/ep*1e4)
        if len(vals)<50:
            print(f"{h:>6}m  (too few valid)"); continue
        g=float(np.mean(vals))
        hh = f"{h}m" if h<60 else f"{h//60}h"
        print(f"{hh:>7} {g:>7.2f} {g-FR_MK:>7.2f} {g-FR_TK:>7.2f}  {len(vals):>7}")

curve(lambda e: True, "ALL entries (baseline)")
curve(lambda e: e[4] is True, "1h-trend ALIGNED")
curve(lambda e: e[4] is True and e[3]>=5, "1h-ALIGNED & ATR>=5bps")
print(f"\ntime {time.time()-t0:.1f}s")
