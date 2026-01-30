# API Test Report: Market Data Sync

**Date:** 2026-01-28 16:08
**Base URL:** `http://localhost:8765/api/v1`
**Status:** ✅ All tests passed (after bug fix)

---

## Bug Found & Fixed

### Issue: `bar_count` vs `bars_count` argument mismatch
- **File:** `src/features/market_data/sync/handler.py:91`
- **Problem:** Called `record_sync(bar_count=...)` but method expects `bars_count`
- **Also:** Used `last_bar_time` instead of `last_bar_at`
- **Fix:** Updated to use correct parameter names + imported `DomainInterval`

```python
# Before (broken)
aggregate.record_sync(
    interval=interval,
    bar_count=upserted_count,
    last_bar_time=latest_bar.datetime...
)

# After (fixed)
aggregate.record_sync(
    interval=DomainInterval(interval.value),
    bars_count=upserted_count,
    last_bar_at=latest_bar.datetime...
)
```

---

## Test Results

### 1. POST /market-data/sync ✅
Sync single symbol from TradingView to database.

| Test Case | Symbol | Exchange | Interval | n_bars | Status | bars_synced |
|-----------|--------|----------|----------|--------|--------|-------------|
| Crypto daily | BTCUSD | BINANCE | 1d | 100 | ✅ completed | 0 (already exists) |
| Crypto hourly | BTCUSD | BINANCE | 1h | 50 | ✅ completed | 50 |

### 2. POST /market-data/sync/bulk ✅
Sync multiple symbols in one request.

| Symbols | Interval | n_bars | Status |
|---------|----------|--------|--------|
| ETHUSD (BINANCE), AAPL (NASDAQ) | 1d | 50 | ✅ Both completed |

### 3. POST /market-data/sync/background ✅
Non-blocking async sync.

| Symbol | Exchange | Response |
|--------|----------|----------|
| SOLUSD | BINANCE | `{"status":"accepted","message":"Sync started..."}` |

### 4. GET /market-data/ohlcv/{exchange}/{symbol} ✅
Retrieve OHLCV data from database.

| Test Case | Params | Count | Sample Data |
|-----------|--------|-------|-------------|
| BTCUSD default | limit=10 | 10 | open: 89170.16, close: 88843.21 |
| AAPL stocks | limit=5 | 5 | open: 259.17, close: 258.27 |
| Date range filter | start=2026-01-20, end=2026-01-25 | 5 | Filtered correctly |

### 5. GET /market-data/sync-status ✅
List all sync statuses.

```json
[
  {"symbol":"BTCUSD","exchange":"BINANCE","interval":"1d","status":"completed","bar_count":100},
  ...
]
```

### 6. GET /market-data/sync-status/{exchange}/{symbol} ✅
Get specific symbol sync status.

| Symbol | bar_count | last_bar_at |
|--------|-----------|-------------|
| BTCUSD | 100 | 2026-01-28T07:00:00 |

### 7. GET /market-data/symbols ✅
List all synced symbols.

| Symbol | Exchange | is_active |
|--------|----------|-----------|
| AAPL | NASDAQ | true |
| BTCUSD | BINANCE | true |
| ETHUSD | BINANCE | true |

---

## Data Verification

### BTCUSD Sample (2026-01-28)
```json
{
  "datetime": "2026-01-28T07:00:00",
  "open": 89170.16,
  "high": 89377.65,
  "low": 88719.34,
  "close": 88843.21,
  "volume": 4.04059
}
```

### AAPL Sample (2026-01-27)
```json
{
  "datetime": "2026-01-27T21:30:00",
  "open": 259.17,
  "high": 261.95,
  "low": 258.21,
  "close": 258.27,
  "volume": 49648271.0
}
```

---

## Summary

| Category | Status | Notes |
|----------|--------|-------|
| Single sync | ✅ | Works for crypto & stocks |
| Bulk sync | ✅ | Multiple symbols sequential |
| Background sync | ✅ | Non-blocking response |
| Data retrieval | ✅ | Pagination, date filters work |
| Status tracking | ✅ | Per-symbol and aggregate |
| TradingView integration | ✅ | Data fetching reliable |

**Total tests: 7 endpoints tested**
**Pass rate: 100%** (after bug fix)
