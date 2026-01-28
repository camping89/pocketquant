# Phase 1: Centralize Constants

## Context Links
- Parent: [plan.md](plan.md)
- Dependencies: None
- Research: [DDD Patterns](research/researcher-ddd-cqrs-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-27 |
| Priority | P1 |
| Status | completed |
| Effort | 1h |

Create single `constants.py` with prefixed sections. Replace all scattered constant definitions across codebase.

## Key Insights

From brainstorm analysis:
- `OHLCV_COLLECTION` defined in 2 places
- `SYNC_STATUS_COLLECTION` defined in 3 places
- `SYMBOLS_COLLECTION` defined in 2 places
- Cache keys hardcoded inline
- TTLs scattered (60s, 300s, 3600s)

## Requirements

### Functional
- Single source of truth for all constants
- Prefixed naming convention for discoverability
- Type hints for IDE support

### Non-Functional
- No runtime overhead (module-level constants)
- Easy grep-ability with prefixes

## Architecture

```
src/common/constants.py
├── COLLECTION_*     # MongoDB collection names
├── CACHE_KEY_*      # Redis key patterns
├── TTL_*            # Cache time-to-live values
├── LIMIT_*          # System limits
└── HEADER_*         # HTTP header names
```

## Related Code Files

### Create
- `src/common/constants.py`

### Modify
- `src/features/market_data/services/data_sync_service.py` - Replace hardcoded collections
- `src/features/market_data/services/quote_service.py` - Replace cache keys/TTLs
- `src/features/market_data/api/routes.py` - Replace collection names
- `src/features/market_data/api/quote_routes.py` - Replace cache keys
- `src/features/market_data/managers/bar_manager.py` - Replace cache keys/TTLs
- `src/features/market_data/jobs/sync_jobs.py` - Replace constants

## Implementation Steps

1. **Audit all constant usages**
   ```bash
   grep -rn "COLLECTION\|_KEY\|_TTL\|5000" src/ --include="*.py"
   ```

2. **Create constants.py with sections**
   ```python
   # src/common/constants.py

   # COLLECTIONS - MongoDB collection names
   COLLECTION_OHLCV = "ohlcv"
   COLLECTION_SYNC_STATUS = "sync_status"
   COLLECTION_SYMBOLS = "symbols"

   # CACHE_KEYS - Redis key patterns (use .format() or f-strings)
   CACHE_KEY_QUOTE_LATEST = "quote:latest:{exchange}:{symbol}"
   CACHE_KEY_BAR_CURRENT = "bar:current:{exchange}:{symbol}:{interval}"
   CACHE_KEY_OHLCV = "ohlcv:{symbol}:{exchange}:{interval}:{limit}"

   # TTL - Cache time-to-live (seconds)
   TTL_QUOTE_LATEST = 60
   TTL_BAR_CURRENT = 300
   TTL_OHLCV_QUERY = 300
   TTL_DEFAULT = 3600

   # LIMITS
   LIMIT_TVDATAFEED_MAX_BARS = 5000
   LIMIT_BULK_SYNC_MAX = 50

   # HEADERS
   HEADER_CORRELATION_ID = "X-Correlation-ID"
   HEADER_IDEMPOTENCY_KEY = "Idempotency-Key"
   ```

3. **Update each file to import from constants**
   - Search: `"ohlcv"` → `COLLECTION_OHLCV`
   - Search: `"sync_status"` → `COLLECTION_SYNC_STATUS`
   - Search: `5000` → `LIMIT_TVDATAFEED_MAX_BARS`
   - Etc.

4. **Run tests to verify no breakage**
   ```bash
   pytest -v
   ```

## Todo List

- [x] Audit all hardcoded constants in codebase
- [x] Create `src/common/constants.py`
- [x] Update `data_sync_service.py` imports
- [x] Update `quote_service.py` imports
- [x] Update `routes.py` imports
- [x] Update `quote_routes.py` imports (no changes needed - uses services)
- [x] Update `bar_manager.py` imports
- [x] Update `sync_jobs.py` imports
- [x] Run tests (verified imports work, no test files exist yet)

## Success Criteria

- [x] Single `constants.py` file with all constants
- [x] No hardcoded collection names outside constants.py
- [x] No hardcoded cache keys outside constants.py
- [x] All tests pass (no tests exist yet, but all imports work)
- [x] grep returns no duplicate definitions

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Missing constant | Low | Low | Comprehensive grep audit |
| Import cycle | Low | Medium | constants.py has no imports |

## Next Steps

After completion:
- Proceed to Phase 2 (Infrastructure Layer)
- Constants ready for use in new infrastructure modules
