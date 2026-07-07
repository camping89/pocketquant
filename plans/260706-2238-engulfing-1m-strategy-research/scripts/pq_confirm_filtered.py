"""Confirm: does 1h-aligned + ATR-floor subset net positive under real first-touch exit, in AND out of sample?"""
import time, bisect
from datetime import datetime
import numpy as np
from pymongo import MongoClient, ASCENDING

URL = "mongodb://pocketquant:***REMOVED***@207.148.79.60:52017/pocketquant?authSource=admin"
db = MongoClient(URL, serverSelectionTimeoutMS=15000)["pocketquant"]
RUN = "019f36d2-5f4f-75cc-95c6-49a7496c3a86"
FR_MK, FR_TK = 4.0, 11.0
SPLIT = datetime(2026, 1, 6)  # ~6/6 split of the year
MAXBARS = 240

t0 = time.time()
bars = list(db["bars"].find({"symbol":"BTCUSDT:BINANCE","interval":"1m","datetime":{"$gte":datetime(2025,7,1),"$lt":datetime(2026,7,8)}},
    {"datetime":1,"high":1,"low":1,"close":1,"_id":0}).sort("datetime", ASCENDING))
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
h1dt=[b["datetime"] for b in h1]; h1cl=np.array([b["close"] for b in h1]); h1up=h1cl>ema(h1cl,20)
def htf_up(t):
    k=bisect.bisect_right(h1dt,t)-1
    return bool(h1up[k]) if k>=0 else None

trades=list(db["backtest_trades"].find({"run_id":RUN},{"entry_time":1,"entry_price":1,"direction":1,"_id":0}))
E=[]
for tr in trades:
    i=idx_of.get(tr["entry_time"])
    if i is None or np.isnan(ATR[i]) or i+1>=n: continue
    ep=tr["entry_price"]; isl=tr["direction"]=="LONG"; up=htf_up(tr["entry_time"])
    if up is None or (up!=isl): continue           # 1h-trend ALIGNED only
    if ATR[i]/ep*1e4 < 5.0: continue               # volatility floor
    E.append((i,ep,isl,ATR[i],dt[i]))
tr_in=[e for e in E if e[4]<SPLIT]; tr_out=[e for e in E if e[4]>=SPLIT]
print(f"filtered entries: {len(E)}  (in={len(tr_in)} out={len(tr_out)})  time {time.time()-t0:.1f}s")

def sim(entries, sl_w, tpfn):
    bps=[]
    for i,ep,isl,atr,_ in entries:
        sld=atr*sl_w; tpd=tpfn(sld,atr)
        j0,j1=i+1,min(i+1+MAXBARS,n); hh=H[j0:j1]; ll=L[j0:j1]
        if isl:
            sh=np.where(ll<=ep-sld)[0]; th=np.where(hh>=ep+tpd)[0]
        else:
            sh=np.where(hh>=ep+sld)[0]; th=np.where(ll<=ep-tpd)[0]
        si=sh[0] if len(sh) else 10**9; ti=th[0] if len(th) else 10**9
        if si==10**9 and ti==10**9:
            last=Cl[j1-1]; move=(last-ep) if isl else (ep-last); b=move/ep*1e4
        elif si<=ti: b=-sld/ep*1e4
        else: b=tpd/ep*1e4
        bps.append(b)
    a=np.array(bps); return dict(n=len(a), wr=float((a>0).mean()), g=float(a.mean()))

SL_W=[2.0,2.5,3.0,4.0]; TP_A=[3.0,5.0,7.0,10.0]; R_M=[1.5,2.0,3.0]
configs=[]
for slw in SL_W:
    for tw in TP_A: configs.append((f"tp={tw:.0f}xATR", slw, (lambda sld,atr,w=tw: atr*w)))
    for r in R_M:   configs.append((f"tp={r:.1f}R", slw, (lambda sld,atr,rr=r: sld*rr)))

# rank on IN-SAMPLE net@maker, then show OUT-OF-SAMPLE
res=[]
for lbl,slw,fn in configs:
    s_in=sim(tr_in,slw,fn); s_out=sim(tr_out,slw,fn)
    res.append((lbl,slw,s_in,s_out))
res.sort(key=lambda x:x[2]["g"]-FR_MK, reverse=True)
print(f"\n== first-touch exit on FILTERED subset. friction maker={FR_MK} taker={FR_TK}. ranked by IN-sample net@maker ==")
print(f"{'cfg':12} {'slW':>4} | {'IN n':>5} {'wr':>4} {'gross':>6} {'net@mk':>7} | {'OUT n':>5} {'wr':>4} {'gross':>6} {'net@mk':>7} {'net@tk':>7}")
for lbl,slw,si,so in res[:10]:
    print(f"{lbl:12} {slw:>4} | {si['n']:>5} {si['wr']:>4.2f} {si['g']:>6.2f} {si['g']-FR_MK:>7.2f} | {so['n']:>5} {so['wr']:>4.2f} {so['g']:>6.2f} {so['g']-FR_MK:>7.2f} {so['g']-FR_TK:>7.2f}")

# annualized sanity for best OOS-consistent cell
print(f"\n== interpretation of top cell ==")
lbl,slw,si,so=res[0]
tot_out = so["n"]*(so["g"]-FR_MK)
print(f"top IN cfg: {lbl} slW={slw}")
print(f"  IN : n={si['n']} net@mk={si['g']-FR_MK:+.2f} bps/trade")
print(f"  OUT: n={so['n']} net@mk={so['g']-FR_MK:+.2f} bps/trade  -> {'HOLDS' if so['g']-FR_MK>0 else 'FAILS out-of-sample'}")
print(f"  OUT total (net@mk): {tot_out:+.0f} bps over {so['n']} trades")
print(f"\ntime {time.time()-t0:.1f}s")
