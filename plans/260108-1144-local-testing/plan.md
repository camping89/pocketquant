---
title: "Local Testing & Validation"
description: "Validate PocketQuant market data infrastructure works locally before VPS deployment"
status: completed
priority: P1
effort: 2h
branch: main
tags: [testing, validation, market-data, infrastructure]
created: 2026-01-08
---

# Plan A: Local Testing & Validation

## Objective

Validate the market data infrastructure works correctly on local environment before VPS deployment.

## Success Criteria

- [ ] App runs without errors on `uvicorn src.main:app --reload`
- [ ] Health endpoint returns 200 OK
- [ ] Can sync 5000 bars of historical AAPL data via `/api/v1/market-data/sync`
- [ ] Real-time quote service starts and receives live quotes
- [ ] Data persists in MongoDB (verify via `ohlcv` collection)
- [ ] Redis cache works for quotes

---

## Phase 1: Environment Setup (15 min)

### Task 1.1: Create Python Virtual Environment

```bash
cd /Users/admin/workspace/_me/pocketquant
python3 -m venv .venv
source .venv/bin/activate
```

**Verification:**
```bash
which python  # Should show .venv/bin/python
python --version  # Should be 3.14+
```

### Task 1.2: Install Dependencies

```bash
pip install -e ".[dev]"
```

**Expected output:** All packages install successfully including:
- fastapi, uvicorn, pydantic
- motor (async MongoDB), pymongo
- redis
- tvdatafeed (TradingView historical data)
- websockets (real-time quotes)
- structlog (logging)

**Potential Issues:**
- `tvdatafeed` may require additional system dependencies
- Check for pip version compatibility

### Task 1.3: Create Environment File

```bash
cp .env.example .env
```

**Edit `.env` for local development:**
```env
ENVIRONMENT=development
DEBUG=true
LOG_FORMAT=console  # Human-readable logs instead of JSON
```

---

## Phase 2: Docker Infrastructure (10 min)

### Task 2.1: Start Docker Services

```bash
docker-compose up -d
```

**Services started:**
| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| MongoDB 7.0 | pocketquant-mongodb | 27017 | OHLCV data storage |
| Redis 7.2 | pocketquant-redis | 6379 | Quote cache |

### Task 2.2: Verify Container Health

```bash
docker-compose ps
```

**Expected:**
- mongodb: Up (healthy)
- redis: Up (healthy)

### Task 2.3: Verify MongoDB Initialization

```bash
docker exec pocketquant-mongodb mongosh -u pocketquant -p pocketquant_dev --authenticationDatabase admin --eval "db.getSiblingDB('pocketquant').getCollectionNames()"
```

**Expected collections:**
- `ohlcv` (with indexes: `idx_ohlcv_unique`, `idx_symbol_interval_datetime`, `idx_datetime`)
- `sync_status`
- `symbols`

### Task 2.4: Verify Redis Connection

```bash
docker exec pocketquant-redis redis-cli ping
```

**Expected:** `PONG`

---

## Phase 3: Application Startup (10 min)

### Task 3.1: Start FastAPI Application

```bash
source .venv/bin/activate
python -m src.main
# Alternative: uvicorn src.main:app --reload
```

**Expected log output (console format):**
```
connecting_to_mongodb database=pocketquant
mongodb_connected database=pocketquant
redis_connected
application_started
Uvicorn running on http://0.0.0.0:8000
```

### Task 3.2: Test Health Endpoint

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development"
}
```

### Task 3.3: Access API Documentation

Open browser: http://localhost:8000/api/v1/docs

**Verify endpoints visible:**
- Market Data: `/market-data/sync`, `/market-data/ohlcv/{exchange}/{symbol}`
- Quotes: `/quotes/start`, `/quotes/subscribe`, `/quotes/latest/{exchange}/{symbol}`

---

## Phase 4: Historical Data Sync Test (20 min)

### Task 4.1: Sync AAPL Historical Data

```bash
curl -X POST http://localhost:8000/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "exchange": "NASDAQ",
    "interval": "1d",
    "n_bars": 5000
  }'
```

**Expected response:**
```json
{
  "symbol": "AAPL",
  "exchange": "NASDAQ",
  "interval": "1d",
  "status": "completed",
  "bars_synced": 5000,
  "total_bars": 5000
}
```

**Potential Issues:**
1. TradingView rate limiting - wait and retry
2. `tvdatafeed` authentication issues - works without login for most symbols
3. Timeout - increase request timeout or use background sync

### Task 4.2: Verify Sync Status

```bash
curl http://localhost:8000/api/v1/market-data/sync-status
```

**Expected:**
```json
[
  {
    "symbol": "AAPL",
    "exchange": "NASDAQ",
    "interval": "1d",
    "status": "completed",
    "bar_count": 5000,
    "last_sync_at": "2026-01-08T..."
  }
]
```

### Task 4.3: Retrieve OHLCV Data via API

```bash
curl "http://localhost:8000/api/v1/market-data/ohlcv/NASDAQ/AAPL?interval=1d&limit=10"
```

**Expected:** Array of 10 OHLCV bars with fields:
- datetime, open, high, low, close, volume

### Task 4.4: Verify Data in MongoDB

```bash
docker exec pocketquant-mongodb mongosh -u pocketquant -p pocketquant_dev --authenticationDatabase admin --eval "
db = db.getSiblingDB('pocketquant');
print('Total OHLCV count:', db.ohlcv.countDocuments({}));
print('AAPL count:', db.ohlcv.countDocuments({symbol: 'AAPL', exchange: 'NASDAQ'}));
print('Sample record:');
printjson(db.ohlcv.findOne({symbol: 'AAPL'}));
"
```

**Expected:**
- Total count >= 5000
- AAPL count = 5000
- Sample record with all OHLCV fields populated

---

## Phase 5: Real-time Quotes Test (20 min)

### Task 5.1: Start Quote Service

```bash
curl -X POST http://localhost:8000/api/v1/quotes/start
```

**Expected response:**
```json
{
  "status": "started",
  "message": "Quote service started"
}
```

**Application logs should show:**
```
quote_service_starting
tradingview_ws_connecting
tradingview_ws_connected session_id=qs_...
quote_service_started
```

### Task 5.2: Check Quote Service Status

```bash
curl http://localhost:8000/api/v1/quotes/status
```

**Expected:**
```json
{
  "running": true,
  "subscription_count": 0,
  "active_symbols": []
}
```

### Task 5.3: Subscribe to AAPL Quotes

```bash
curl -X POST http://localhost:8000/api/v1/quotes/subscribe \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "exchange": "NASDAQ"}'
```

**Expected:**
```json
{
  "subscription_key": "NASDAQ:AAPL",
  "message": "Subscribed to NASDAQ:AAPL"
}
```

### Task 5.4: Wait for Quote Data (Market Hours Only)

> **Note:** TradingView real-time quotes only work during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)

Wait 5-10 seconds, then:

```bash
curl http://localhost:8000/api/v1/quotes/latest/NASDAQ/AAPL
```

**Expected (during market hours):**
```json
{
  "symbol": "AAPL",
  "exchange": "NASDAQ",
  "timestamp": "2026-01-08T...",
  "last_price": 185.50,
  "bid": 185.49,
  "ask": 185.51,
  "volume": 1234567,
  "change": 1.25,
  "change_percent": 0.68
}
```

**Outside market hours:** May return 404 or stale data

### Task 5.5: Verify Redis Cache

```bash
docker exec pocketquant-redis redis-cli KEYS "quote:*"
```

**Expected:** `quote:latest:NASDAQ:AAPL`

```bash
docker exec pocketquant-redis redis-cli GET "quote:latest:NASDAQ:AAPL"
```

**Expected:** JSON with latest quote data

### Task 5.6: Test Current Bar Aggregation

```bash
curl "http://localhost:8000/api/v1/quotes/current-bar/NASDAQ/AAPL?interval=1m"
```

**Expected (during market hours):** In-progress 1-minute bar being built from ticks

### Task 5.7: Stop Quote Service

```bash
curl -X POST http://localhost:8000/api/v1/quotes/stop
```

**Expected:**
```json
{
  "status": "stopped",
  "message": "Quote service stopped",
  "bars_saved": 0
}
```

---

## Phase 6: Additional Validation (15 min)

### Task 6.1: Test Different Intervals

```bash
# Sync hourly data
curl -X POST http://localhost:8000/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "exchange": "NASDAQ", "interval": "1h", "n_bars": 1000}'
```

### Task 6.2: Test Multiple Symbols

```bash
curl -X POST http://localhost:8000/api/v1/market-data/sync/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": [
      {"symbol": "MSFT", "exchange": "NASDAQ"},
      {"symbol": "GOOGL", "exchange": "NASDAQ"}
    ],
    "interval": "1d",
    "n_bars": 100
  }'
```

### Task 6.3: Test Background Sync

```bash
curl -X POST http://localhost:8000/api/v1/market-data/sync/background \
  -H "Content-Type: application/json" \
  -d '{"symbol": "TSLA", "exchange": "NASDAQ", "interval": "1d", "n_bars": 1000}'
```

**Expected:** Immediate `{"status": "accepted", ...}` response, sync runs in background

### Task 6.4: List All Tracked Symbols

```bash
curl http://localhost:8000/api/v1/market-data/symbols
```

### Task 6.5: Check Background Jobs

```bash
curl http://localhost:8000/api/v1/system/jobs
```

---

## Phase 7: Cleanup & Documentation (10 min)

### Task 7.1: Stop Application

Press `Ctrl+C` in terminal running uvicorn

**Verify graceful shutdown in logs:**
```
application_stopping
quote_service_stopping (if running)
mongodb_disconnected
redis_disconnected
application_stopped
```

### Task 7.2: Stop Docker Containers

```bash
# Keep data persistent
docker-compose stop

# Or remove containers and volumes (loses data)
# docker-compose down -v
```

### Task 7.3: Document Issues Found

Create file: `plans/260108-1144-local-testing/issues.md`

Template:
```markdown
# Issues Found During Local Testing

## Date: 2026-01-08

### Critical Issues
- [ ] Issue 1...

### Warnings
- [ ] Warning 1...

### Notes
- Note 1...
```

---

## Troubleshooting Guide

### MongoDB Connection Failed

**Symptom:** `ServerSelectionTimeoutError`

**Solutions:**
1. Check container is running: `docker-compose ps`
2. Verify credentials in `.env` match `docker-compose.yml`
3. Check port 27017 is not blocked: `lsof -i :27017`

### Redis Connection Failed

**Symptom:** `ConnectionRefusedError` on Redis

**Solutions:**
1. Check container: `docker exec pocketquant-redis redis-cli ping`
2. Verify port 6379 is free

### TradingView Fetch Returns Empty

**Symptom:** `No data returned from provider`

**Causes:**
1. Invalid symbol/exchange combination
2. TradingView rate limiting
3. Network issues

**Solutions:**
1. Try different symbol (AAPL is usually reliable)
2. Wait 30 seconds and retry
3. Check network connectivity

### WebSocket Connection Failed

**Symptom:** Quote service starts but no quotes received

**Solutions:**
1. Verify market is open (9:30 AM - 4:00 PM ET)
2. Check firewall allows outbound wss:// connections
3. Try crypto symbol (BTCUSD on BINANCE) for 24/7 testing

### Import Errors

**Symptom:** `ModuleNotFoundError`

**Solutions:**
1. Ensure venv is activated: `source .venv/bin/activate`
2. Reinstall: `pip install -e ".[dev]"`
3. Check Python version: `python --version` (needs 3.14+)

---

## Dependencies Between Phases

```
Phase 1 (Env Setup)
    ↓
Phase 2 (Docker)
    ↓
Phase 3 (App Startup) ← Requires Phase 1 + 2
    ↓
Phase 4 (Historical Sync) ← Requires Phase 3
    ↓
Phase 5 (Real-time Quotes) ← Requires Phase 3
    ↓
Phase 6 (Additional Tests) ← Requires Phase 3
    ↓
Phase 7 (Cleanup)
```

---

## Estimated Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| 1. Environment Setup | 15 min | 15 min |
| 2. Docker Infrastructure | 10 min | 25 min |
| 3. Application Startup | 10 min | 35 min |
| 4. Historical Data Sync | 20 min | 55 min |
| 5. Real-time Quotes | 20 min | 1h 15min |
| 6. Additional Validation | 15 min | 1h 30min |
| 7. Cleanup & Docs | 10 min | 1h 40min |
| **Buffer** | 20 min | **2h** |

---

## Checklist Summary

```
[ ] Phase 1: Environment Setup
    [ ] 1.1 Python venv created
    [ ] 1.2 Dependencies installed
    [ ] 1.3 .env configured

[ ] Phase 2: Docker Infrastructure
    [ ] 2.1 docker-compose up
    [ ] 2.2 Containers healthy
    [ ] 2.3 MongoDB initialized
    [ ] 2.4 Redis responding

[ ] Phase 3: Application Startup
    [ ] 3.1 App starts without errors
    [ ] 3.2 Health endpoint returns OK
    [ ] 3.3 API docs accessible

[ ] Phase 4: Historical Data Sync
    [ ] 4.1 AAPL sync completes (5000 bars)
    [ ] 4.2 Sync status shows completed
    [ ] 4.3 OHLCV API returns data
    [ ] 4.4 MongoDB has data

[ ] Phase 5: Real-time Quotes
    [ ] 5.1 Quote service starts
    [ ] 5.2 Service status shows running
    [ ] 5.3 Subscription succeeds
    [ ] 5.4 Quotes received (market hours)
    [ ] 5.5 Redis has cached quotes
    [ ] 5.6 Current bar works
    [ ] 5.7 Service stops cleanly

[ ] Phase 6: Additional Validation
    [ ] 6.1 Different intervals work
    [ ] 6.2 Bulk sync works
    [ ] 6.3 Background sync works
    [ ] 6.4 Symbols list works
    [ ] 6.5 Jobs endpoint works

[ ] Phase 7: Cleanup
    [ ] 7.1 Graceful shutdown
    [ ] 7.2 Containers stopped
    [ ] 7.3 Issues documented
```
