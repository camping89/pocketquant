# Phase 6: Manual Testing

## Context Links
- [Plan Overview](plan.md)
- [Phase 5: Code Quality](phase-05-code-quality-docs.md)
- [main.py](../../src/main.py)
- [API Routes](../../src/features/market_data/api/)

## Overview
- **Priority:** P1 (validation)
- **Status:** pending
- **Effort:** 45m
- **Description:** Manually verify all MongoDB operations work correctly with PyMongo Async

## Key Insights
- PyMongo Async connection errors surface during operations, not at init
- Need to verify actual database operations, not just startup
- WebSocket quotes also depend on MongoDB for bar storage
- Background jobs use MongoDB for sync operations

## Requirements

### Functional
- Application starts successfully
- Database connection established
- All CRUD operations work
- Background jobs execute

### Non-Functional
- Performance not degraded (PyMongo should be faster)
- No memory leaks visible during testing

## Architecture
End-to-end validation. No code changes.

## Related Code Files

### Key Components to Test
| Component | File | Test Focus |
|-----------|------|------------|
| Database Singleton | `src/common/database/connection.py` | connect(), get_collection() |
| OHLCV Repository | `src/features/market_data/repositories/ohlcv_repository.py` | upsert_many(), get_bars() |
| Symbol Repository | `src/features/market_data/repositories/symbol_repository.py` | upsert(), get_all() |
| Sync Service | `src/features/market_data/services/data_sync_service.py` | Full sync flow |
| Quote Service | `src/features/market_data/services/quote_service.py` | Bar aggregation |

## Pre-Test Setup

### 1. Start Infrastructure
```bash
docker compose -f docker/compose.yml up -d
```

### 2. Verify MongoDB is Running
```bash
docker compose -f docker/compose.yml ps
# mongodb should be "running"
```

### 3. Set Environment
```bash
# Copy .env.example if .env doesn't exist
cp .env.example .env
# Edit as needed
```

## Test Cases

### Test 1: Application Startup

**Command:**
```bash
python -m src.main
```

**Expected Output:**
```
INFO     connecting_to_mongodb database=pocketquant
INFO     mongodb_connected database=pocketquant
INFO     Application startup complete
```

**Pass Criteria:**
- No `ModuleNotFoundError` for motor
- `mongodb_connected` log appears
- Server starts on port 8765

### Test 2: Health Check

**Command:**
```bash
curl http://localhost:8765/health
```

**Expected:**
```json
{"status": "healthy"}
```

### Test 3: Manual Sync (Database Write)

**Command:**
```bash
curl -X POST "http://localhost:8765/api/v1/market-data/sync" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "exchange": "NASDAQ", "interval": "1d", "n_bars": 10}'
```

**Expected:** Sync completes with bar count > 0

**Validates:**
- OHLCVRepository.upsert_many() (bulk_write)
- OHLCVRepository.update_sync_status() (update_one)
- Cache invalidation

### Test 4: Fetch Historical Data (Database Read)

**Command:**
```bash
curl "http://localhost:8765/api/v1/market-data/ohlcv/NASDAQ/AAPL?interval=1d&limit=5"
```

**Expected:** JSON array with OHLCV data

**Validates:**
- OHLCVRepository.get_bars() (find with cursor)
- `async for doc in cursor` pattern

### Test 5: Get Sync Status

**Command:**
```bash
curl "http://localhost:8765/api/v1/market-data/sync-status"
```

**Expected:** Array with sync status entries

**Validates:**
- OHLCVRepository.get_all_sync_statuses() (find all)

### Test 6: Symbol Operations

**Command:**
```bash
# List symbols
curl "http://localhost:8765/api/v1/market-data/symbols"
```

**Expected:** Array of tracked symbols

**Validates:**
- SymbolRepository.get_all() (find with sort)

### Test 7: Quote Service Start (WebSocket)

**Command:**
```bash
curl -X POST "http://localhost:8765/api/v1/quotes/start"
```

**Expected:** `{"status": "started"}` or `{"status": "already_running"}`

**Validates:**
- QuoteService integration (uses Database indirectly via QuoteAggregator)

### Test 8: Background Jobs Status

**Command:**
```bash
curl "http://localhost:8765/api/v1/system/jobs"
```

**Expected:** List of scheduled jobs

**Validates:**
- JobScheduler still works (uses MongoDB for sync jobs)

### Test 9: Graceful Shutdown

**Action:** Send SIGINT (Ctrl+C) to running server

**Expected Logs:**
```
INFO     Application shutdown started
INFO     mongodb_disconnected
```

**Pass Criteria:**
- No errors during shutdown
- `mongodb_disconnected` log appears
- Process exits cleanly

## Test Results Template

| Test | Status | Notes |
|------|--------|-------|
| 1. Application Startup | [ ] Pass / [ ] Fail | |
| 2. Health Check | [ ] Pass / [ ] Fail | |
| 3. Manual Sync | [ ] Pass / [ ] Fail | |
| 4. Fetch Historical | [ ] Pass / [ ] Fail | |
| 5. Sync Status | [ ] Pass / [ ] Fail | |
| 6. Symbol Operations | [ ] Pass / [ ] Fail | |
| 7. Quote Service | [ ] Pass / [ ] Fail | |
| 8. Background Jobs | [ ] Pass / [ ] Fail | |
| 9. Graceful Shutdown | [ ] Pass / [ ] Fail | |

## Todo List
- [ ] Start Docker infrastructure
- [ ] Test 1: Application startup
- [ ] Test 2: Health check endpoint
- [ ] Test 3: Manual sync (write operations)
- [ ] Test 4: Fetch historical data (read operations)
- [ ] Test 5: Get sync status
- [ ] Test 6: Symbol operations
- [ ] Test 7: Quote service start
- [ ] Test 8: Background jobs status
- [ ] Test 9: Graceful shutdown
- [ ] Document any failures and fixes needed

## Success Criteria
- All 9 tests pass
- No Motor-related errors in logs
- No performance regression observed
- Clean shutdown without errors

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Connection failure at runtime | Low | High | Check connection string format |
| Cursor exhaustion | Very Low | Medium | Verify `async for` works |
| Pool exhaustion | Very Low | Low | Monitor connections during tests |

## Troubleshooting Guide

### Error: ModuleNotFoundError: motor
**Cause:** Motor still being imported somewhere
**Fix:** Run `grep -r "motor" src/` and update missed files

### Error: Cannot connect to MongoDB
**Cause:** Docker not running or wrong connection string
**Fix:** Check `docker compose ps` and `.env` file

### Error: Authentication failed
**Cause:** Credentials mismatch
**Fix:** Verify `authSource=admin` in connection string

### Error: "Database not connected"
**Cause:** connect() not called or failed silently
**Fix:** Check startup logs for connection errors

## Security Considerations
- Test with non-production credentials
- Don't commit test data
- Clear test data after validation

## Next Steps
After all tests pass:
1. Update plan.md status to `completed`
2. Consider creating automated tests for regression
3. Monitor production deployment closely
