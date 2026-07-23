"""Prefetch bars (multi-TF) + engulfing entries to local cache so agents don't hit prod DB repeatedly."""
import os
from datetime import datetime
import numpy as np
from pymongo import MongoClient, ASCENDING

import os; URL = os.environ["MONGODB_URL"]  # do NOT hardcode; export MONGODB_URL from .env
db = MongoClient(URL, serverSelectionTimeoutMS=20000)["pocketquant"]
RUN = "019f36d2-5f4f-75cc-95c6-49a7496c3a86"
OUT = "/tmp/pq_cache"
os.makedirs(OUT, exist_ok=True)
LO, HI = datetime(2025, 6, 1), datetime(2026, 7, 8)  # pad start for indicator warmup

def dump_tf(tf):
    rows = list(db["bars"].find(
        {"symbol": "BTCUSDT:BINANCE", "interval": tf, "datetime": {"$gte": LO, "$lt": HI}},
        {"datetime": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "_id": 0}
    ).sort("datetime", ASCENDING))
    if not rows:
        print(f"{tf}: EMPTY"); return
    ts = np.array([r["datetime"] for r in rows], dtype="datetime64[s]").astype("int64")
    o = np.array([r["open"] for r in rows]); h = np.array([r["high"] for r in rows])
    l = np.array([r["low"] for r in rows]); c = np.array([r["close"] for r in rows])
    v = np.array([r.get("volume", 0.0) for r in rows])
    np.savez(f"{OUT}/bars_{tf}.npz", ts=ts, o=o, h=h, l=l, c=c, v=v)
    print(f"{tf}: {len(rows)} bars  {rows[0]['datetime']} -> {rows[-1]['datetime']}")

for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
    dump_tf(tf)

# entries from the real backtest run
tr = list(db["backtest_trades"].find({"run_id": RUN},
    {"entry_time": 1, "entry_price": 1, "direction": 1, "exit_time": 1, "exit_price": 1,
     "sl_price": 1, "tp_price": 1, "quantity": 1, "pnl": 1, "commission": 1, "_id": 0}))
ets = np.array([r["entry_time"] for r in tr], dtype="datetime64[s]").astype("int64")
ep = np.array([r["entry_price"] for r in tr]); islong = np.array([r["direction"] == "LONG" for r in tr])
sl = np.array([r["sl_price"] for r in tr]); tp = np.array([r["tp_price"] for r in tr])
qty = np.array([r["quantity"] for r in tr]); pnl = np.array([r["pnl"] for r in tr]); comm = np.array([r["commission"] for r in tr])
np.savez(f"{OUT}/entries.npz", ets=ets, ep=ep, islong=islong, sl=sl, tp=tp, qty=qty, pnl=pnl, comm=comm)
print(f"entries: {len(tr)}")
print("cache dir:", OUT, os.listdir(OUT))
