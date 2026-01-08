# Issues Found During Local Testing

## Date: 2026-01-08

### Critical Issues (Fixed)

1. **Python 3.14 Pydantic Compatibility**
   - File: `src/features/market_data/models/ohlcv.py`, `quote.py`
   - Issue: Field name `datetime` conflicts with `datetime` type import
   - Fix: Aliased import as `from datetime import datetime as dt`

2. **MongoDB $set/$setOnInsert Conflict**
   - Files: `src/features/market_data/repositories/ohlcv_repository.py`, `symbol_repository.py`
   - Issue: `created_at` in both `$set` and `$setOnInsert` causes MongoDB error
   - Fix: Pop `created_at` from `$set` doc, only use in `$setOnInsert`

3. **APScheduler IntervalTrigger None Values**
   - File: `src/common/jobs/scheduler.py`
   - Issue: IntervalTrigger doesn't accept `None` for seconds/minutes/hours
   - Fix: Build trigger kwargs dict, only include non-None values

4. **FastAPI Parameter Ordering**
   - File: `src/features/market_data/api/quote_routes.py`
   - Issue: Parameter with default after parameter without default
   - Fix: Reordered service dependency before interval parameter

### Known Limitations

1. **TradingView WebSocket Blocked (HTTP 403)**
   - Real-time quotes feature requires:
     - TradingView premium credentials, OR
     - Alternative data provider (Polygon.io, Alpaca, etc.)
   - Historical data sync works without credentials

2. **tvdatafeed Not on PyPI**
   - Must install from GitHub: `git+https://github.com/rongardF/tvdatafeed.git`
   - Required `tool.hatch.metadata.allow-direct-references = true` in pyproject.toml

### Warnings

1. **docker-compose.yml version attribute obsolete**
   - Can remove `version: "3.9"` line

### Successful Tests

- [x] Environment setup (Python 3.14, venv, deps)
- [x] Docker infrastructure (MongoDB 7.0, Redis 7.2)
- [x] App startup with health check
- [x] Historical data sync (1000 AAPL daily bars)
- [x] Different intervals (1h sync works)
- [x] OHLCV API endpoints
- [x] Symbol tracking
- [x] API documentation (/api/v1/docs)
- [ ] Real-time quotes (blocked by TradingView 403)

### Recommendations

1. Consider adding alternative data providers for real-time quotes
2. Add proper error messages when TradingView WS fails
3. Clear old error messages from sync_status after successful sync
