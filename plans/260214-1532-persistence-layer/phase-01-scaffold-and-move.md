# Phase 1: Scaffold src/persistence/ and Move Files

## Priority: P1 | Status: pending

## Overview
Create the new `src/persistence/` package, copy all files from `src/infrastructure/persistence/`, and update the re-export shims so existing imports keep working throughout the migration.

## Key Insight
The re-export shims (`src/common/database/__init__.py`, `src/common/cache/__init__.py`, `src/infrastructure/__init__.py`) import from `src.infrastructure.persistence`. Updating these to `src.persistence` first means all downstream code continues working without touching every import yet.

## Context Links
- Source: `src/infrastructure/persistence/` (mongodb.py, redis.py, repos/, schemas/)
- Re-exports: `src/common/database/__init__.py`, `src/common/cache/__init__.py`
- Infra barrel: `src/infrastructure/__init__.py`

## Related Code Files

### Files to CREATE
```
src/persistence/__init__.py              - Exports Database, Cache, get_database, get_cache
src/persistence/mongodb.py               - Copy from infrastructure/persistence/mongodb.py
src/persistence/redis.py                 - Copy from infrastructure/persistence/redis.py
src/persistence/repositories/__init__.py - Empty
src/persistence/repositories/order_repository.py
src/persistence/repositories/position_repository.py
src/persistence/repositories/backtest_repository.py
src/persistence/schemas/__init__.py      - Empty
src/persistence/schemas/ohlcv_schema.py
src/persistence/schemas/order_schema.py
src/persistence/schemas/position_schema.py
src/persistence/schemas/quote_schema.py
src/persistence/schemas/symbol_schema.py
```

### Files to MODIFY
```
src/common/database/__init__.py          - Point to src.persistence
src/common/cache/__init__.py             - Point to src.persistence
src/infrastructure/__init__.py           - Point to src.persistence
src/common/health/checks.py             - Point to src.persistence
src/common/idempotency/middleware.py     - Point to src.persistence
src/common/rate_limit/middleware.py      - Point to src.persistence
```

### Files to MODIFY (direct `from src.infrastructure.persistence` imports)
Update all 30+ import lines across these files to use `src.persistence`:
```
src/main.py                              - 3 repo imports
src/features/backtesting/__init__.py     - BacktestRepository import
src/features/backtesting/get_result/handler.py
src/features/backtesting/list_results/handler.py
src/features/backtesting/get_optimization/handler.py  (uses src.common.database -- no change yet)
src/features/backtesting/optimize/handler.py           (uses src.common.database -- no change yet)
src/application/trading/order_manager.py
src/application/trading/position_tracker.py
src/application/backtesting/backtest_runner.py
src/application/backtesting/historical_replay_engine.py
src/application/market_data/bar_manager.py
src/application/market_data/sync_jobs.py
src/application/market_data/quote_service.py
src/features/market_data/sync/sync_one/handler.py
src/features/market_data/ohlcv/get_ohlcv/handler.py
src/features/market_data/ohlcv/get_ohlcv/route.py
src/features/market_data/quotes/dto.py
src/features/market_data/quotes/get_latest/handler.py
src/features/market_data/quotes/get_all/handler.py
src/features/market_data/status/get_sync_status/handler.py
src/features/market_data/status/get_symbol_sync_status/handler.py
src/infrastructure/tradingview/provider.py
src/infrastructure/tradingview/base.py
```

## Implementation Steps

1. **Create `src/persistence/` directory structure**
   ```
   src/persistence/
   ├── __init__.py
   ├── mongodb.py
   ├── redis.py
   ├── repositories/
   │   ├── __init__.py
   │   ├── order_repository.py
   │   ├── position_repository.py
   │   └── backtest_repository.py
   └── schemas/
       ├── __init__.py
       ├── ohlcv_schema.py
       ├── order_schema.py
       ├── position_schema.py
       ├── quote_schema.py
       └── symbol_schema.py
   ```

2. **Copy files verbatim** from `src/infrastructure/persistence/` to `src/persistence/`
   - mongodb.py, redis.py -- no internal import changes needed (they import from src.common, src.config)
   - All schemas -- no internal import changes needed (they import from src.domain)
   - Repositories -- update internal imports:
     - `from src.infrastructure.persistence.schemas.X` -> `from src.persistence.schemas.X`
     - `from src.common.database import Database` stays (re-export shim will point here)

3. **Update `src/persistence/__init__.py`**
   ```python
   """Persistence layer - Database, Cache, repositories, schemas."""
   from src.persistence.mongodb import Database, get_database
   from src.persistence.redis import Cache, get_cache

   __all__ = ["Database", "Cache", "get_database", "get_cache"]
   ```

4. **Update re-export shims** to point to new location:
   - `src/common/database/__init__.py`: `from src.persistence import Database, get_database`
   - `src/common/cache/__init__.py`: `from src.persistence import Cache, get_cache`
   - `src/infrastructure/__init__.py`: `from src.persistence import Cache, Database`
   - `src/common/health/checks.py`: `from src.persistence import Cache, Database`
   - `src/common/idempotency/middleware.py`: `from src.persistence import Cache`
   - `src/common/rate_limit/middleware.py`: `from src.persistence import Cache`

5. **Update all direct `from src.infrastructure.persistence` imports** across entire codebase to `from src.persistence` (see file list above). This is a bulk find-and-replace:
   - `from src.infrastructure.persistence.repositories.X` -> `from src.persistence.repositories.X`
   - `from src.infrastructure.persistence.schemas.X` -> `from src.persistence.schemas.X`
   - `from src.infrastructure.persistence import X` -> `from src.persistence import X`

6. **Run tests**: `pytest` -- all 60 must pass

7. **Keep `src/infrastructure/persistence/` for now** -- delete in Phase 3 after all references confirmed gone

## Todo
- [ ] Create src/persistence/ package with all files
- [ ] Update internal imports in copied repository files
- [ ] Update re-export shims (common/database, common/cache, infrastructure/__init__)
- [ ] Update all direct infrastructure.persistence imports across codebase
- [ ] Run `pytest` -- 60/60 pass
- [ ] Run `ruff check src/` -- no import errors

## Success Criteria
- All imports resolve through `src.persistence` (not `src.infrastructure.persistence`)
- Re-export shims (`src.common.database`, `src.common.cache`) still work
- All 60 tests pass
- Old `src/infrastructure/persistence/` still exists but is no longer imported by anything
