---
title: "Volume aggregation patterns + MongoDB audit queries"
date: 2026-05-07 19:57 +07
slug: volume-audit-research
status: completed
type: researcher
related:
  - plans/reports/brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md
  - plans/260507-1835-vps-bars-mismatch-tv-pro-fix/phase-02-volume-baseline-fix.md
---

# Research: Volume Aggregation + Audit Query Patterns

## Topic 1: Volume Aggregation from Cumulative Streams

### Problem Context
TradingView WS `quote.volume` = **cumulative session volume** (not delta per trade). Must compute per-bar volume as `bar_volume = current_cumulative - baseline_at_bar_open`.

### Session Reset Boundary
- **Binance spot/futures:** UTC midnight (00:00 UTC)
- **Behavior:** Cumulative resets to ~0 at session boundary; detection: `current_cumulative < previous_baseline`
- **Data:** [CoinAPI session boundaries](https://www.coinapi.io/blog/top-10-questions-about-ohlcv-and-tick-data), [Binance documentation](https://medium.com/geekculture/this-is-why-you-should-begin-to-trade-crypto-at-00-00-utc-on-binance-d39be5578a89)

### Industry Patterns (CCXT, python-binance)
- **CCXT:** Exposes cumulative trades via REST; real-time streams handle internally
- **python-binance:** `@klines` WebSocket provides `quote_asset_volume` (cumulative) + delta computation happens at aggregation level
- **Key insight:** Libraries DON'T expose raw cumulative directly to user; aggregation is black-box. Our case (raw TV feed) = manual handling.
- **Reference:** [CCXT Binance docs](https://docs.ccxt.com/exchanges/binance), [Medium: Tick to OHLC conversion](https://medium.com/@gabriele.deri/maximizing-trading-potential-how-to-convert-raw-tick-data-to-ohlc-candles-with-buy-and-sell-volume-46558cdcf94a)

### Edge Cases & Fixes
| Case | Handling |
|------|----------|
| **Negative diff** (`current < baseline`) | Session reset OR broadcaster bug. Detect: `current < baseline` → reset baseline to current, compute delta from 0 |
| **First tick of bar** | Set `baseline = current_cumulative`; bar starts at 0 volume |
| **Cross-bar carryover** | Not applicable; each bar gets fresh baseline from first tick |

### Code Skeleton: BarBuilder
```python
class BarBuilder:
    def __init__(self):
        self._volume_baseline = None  # cumulative at bar open
        self.volume = 0  # aggregated delta for this bar
    
    def add_tick(self, price: float, cumulative_volume: float, ts: datetime):
        """Handle cumulative volume from TV WS."""
        if self.open is None:  # First tick = bar open
            self._volume_baseline = cumulative_volume
            self.volume = 0
        else:
            # Normal case: delta from baseline
            delta = cumulative_volume - self._volume_baseline
            
            # Detect session reset (cumulative went backward)
            if delta < 0:
                # Session boundary: reset baseline, start fresh
                self._volume_baseline = cumulative_volume
                self.volume = 0
            else:
                self.volume = max(0, delta)  # Clamp negatives
```

---

## Topic 2: MongoDB Audit Query Patterns

### Goal
Count "garbage bars" across ~1.5M docs (50 symbols × 30 days × 1440 1m-bars/day):
- `O == H == L == C` (flat bars)
- `volume == 0`
- `volume > threshold` (per-interval anomalies)

### Index Strategy
**Compound index (ESR rule):** Match conditions first, then date range
```javascript
db.bars.createIndex({
    symbol: 1,
    exchange: 1,
    interval: 1,
    datetime: 1  // Range filter last
})
```
This allows `$match` stage to use index for date range filtering before aggregation.

**Reference:** [MongoDB aggregation optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/), [Compound index strategy](https://blog.poespas.me/posts/2025/03/06/optimize-mongo-aggregation-pipeline-performance-large-datasets/)

### PyMongo Aggregation Skeleton
```python
from pymongo import MongoClient
from datetime import datetime, timedelta

def audit_bar_quality(db, symbol: str, days_back: int = 30):
    """Count garbage bars by category."""
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)
    
    pipeline = [
        # Stage 1: Filter by symbol and date range (uses index)
        {
            "$match": {
                "symbol": symbol,
                "datetime": {"$gte": cutoff_date}
            }
        },
        # Stage 2: Classify bars
        {
            "$project": {
                "symbol": 1,
                "interval": 1,
                "datetime": 1,
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 1,
                "is_flat": {
                    "$and": [
                        {"$eq": ["$open", "$high"]},
                        {"$eq": ["$high", "$low"]},
                        {"$eq": ["$low", "$close"]}
                    ]
                },
                "is_zero_volume": {"$eq": ["$volume", 0]},
                "is_abnormal_volume": {"$gt": ["$volume", 5000]}  # Per-interval threshold
            }
        },
        # Stage 3: Group by interval, count by category
        {
            "$group": {
                "_id": "$interval",
                "total": {"$sum": 1},
                "flat_bars": {"$sum": {"$cond": ["$is_flat", 1, 0]}},
                "zero_volume": {"$sum": {"$cond": ["$is_zero_volume", 1, 0]}},
                "abnormal_volume": {"$sum": {"$cond": ["$is_abnormal_volume", 1, 0]}}
            }
        },
        # Stage 4: Compute percentages
        {
            "$project": {
                "_id": 1,
                "total": 1,
                "flat_bars": 1,
                "zero_volume": 1,
                "abnormal_volume": 1,
                "flat_pct": {
                    "$multiply": [
                        {"$divide": ["$flat_bars", "$total"]},
                        100
                    ]
                },
                "zero_vol_pct": {
                    "$multiply": [
                        {"$divide": ["$zero_volume", "$total"]},
                        100
                    ]
                }
            }
        },
        # Stage 5: Sort by interval
        {"$sort": {"_id": 1}}
    ]
    
    results = list(db.bars.aggregate(pipeline, allowDiskUse=True))
    return results
```

### Performance Notes
- **allowDiskUse=True:** Enables spill-to-disk if intermediate result > 100MB (required for large 30-day scans)
- **Index usage:** Pipeline will use compound index for initial `$match` + `datetime` range
- **Memory:** ~1.5M docs × 300 bytes ≈ 450MB intermediate → disk spill likely; acceptable latency 2-5 min

### Output Example
```
[
    {
        "_id": "1m",
        "total": 43200,
        "flat_bars": 412,
        "zero_volume": 2104,
        "abnormal_volume": 3,
        "flat_pct": 0.95,
        "zero_vol_pct": 4.87
    }
]
```

**Reference:** [PyMongo aggregation docs](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/aggregation/), [Pipeline memory management](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)

---

## Cross-Topic Insight: BarBuilder State vs Session Tracker

**Decision:** Store `_volume_baseline` **in BarBuilder instance** (not separate session tracker).

**Rationale:**
- Baseline is bar-specific, not session-specific (each new bar resets)
- Decouples bar logic from session management; simpler state machine
- Session reset detected inline: `if delta < 0 → reset baseline`
- Easier to test (unit test single bar) vs global session state

---

## Unresolved questions

1. **TV session token rotation:** Does TradingView Pro session expire mid-day? Affects backfill script error handling.
2. **Threshold per-interval:** Is 5000 BTC/min reasonable, or should use exchange-specific caps? (spot vs futures liquidity differs)
3. **Garbage bar decision:** If audit shows >10% flat bars, re-sync entire month, or targeted ranges only?

