"""Prefetch bars for multiple symbols into per-symbol caches /tmp/pq_cache_{code}.

Read-only against prod Mongo (MONGODB_URL from env; ENABLE_JOBS irrelevant — we
only read `bars`). One cache dir per symbol so pq_structure_lib.use_cache() can
switch between them cleanly. Entries are NOT fetched (structure research uses the
proxy detector, not the old 8629 real-entry set).
"""

import os
from datetime import datetime

import numpy as np
from pymongo import ASCENDING, MongoClient

URL = os.environ["MONGODB_URL"]
db = MongoClient(URL, serverSelectionTimeoutMS=20000)["pocketquant"]
LO, HI = datetime(2024, 7, 1), datetime(2026, 7, 8)
SYMBOLS = {"BTCUSDT": "BTCUSDT:BINANCE", "ETHUSDT": "ETHUSDT:BINANCE", "SOLUSDT": "SOLUSDT:BINANCE"}
TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]


def dump(code: str, composite: str) -> None:
    out = f"/tmp/pq_cache_{code}"
    os.makedirs(out, exist_ok=True)
    for tf in TFS:
        rows = list(
            db["bars"]
            .find(
                {"symbol": composite, "interval": tf, "datetime": {"$gte": LO, "$lt": HI}},
                {"datetime": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "_id": 0},
            )
            .sort("datetime", ASCENDING)
        )
        if not rows:
            print(f"  {code} {tf}: EMPTY")
            continue
        ts = np.array([r["datetime"] for r in rows], dtype="datetime64[s]").astype("int64")
        o = np.array([r["open"] for r in rows])
        h = np.array([r["high"] for r in rows])
        l = np.array([r["low"] for r in rows])
        c = np.array([r["close"] for r in rows])
        v = np.array([r.get("volume", 0.0) for r in rows])
        np.savez(f"{out}/bars_{tf}.npz", ts=ts, o=o, h=h, l=l, c=c, v=v)
        print(f"  {code} {tf}: {len(rows):>7} bars  {rows[0]['datetime']:%Y-%m-%d} -> {rows[-1]['datetime']:%Y-%m-%d}")


if __name__ == "__main__":
    for code, comp in SYMBOLS.items():
        print(f"[{code}]")
        dump(code, comp)
    print("done.")
