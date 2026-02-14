# Phase 5: Migrate Market Data

## Context
- [Brainstorm](../reports/brainstorm-260214-1326-clean-architecture-refactor.md)
- [Phase 4](./phase-04-migrate-backtesting.md) must complete first

## Overview
- **Priority:** P1
- **Status:** Completed
- **Effort:** 4h
- **Description:** Migrate `features/market_data/base/` and `features/market_data/repositories/` — largest feature (14 ops), most entangled. Includes managers, jobs, providers, models, repositories, and quote_service.

## Key Insights
- `bar_builder.py` — PURE but **already duplicated** in `domain/ohlcv/services/bar_builder.py`. Consolidate: keep domain version, delete feature version.
- `bar_manager.py` — I/O heavy (Cache, Database, logging) → `application/market_data/`
- `sync_jobs.py` — I/O (JobScheduler, Mediator, Database) → `application/market_data/`
- `quote_service.py` — I/O (WebSocket, Cache, asyncio) → `application/market_data/`
- `providers/__init__.py` — Re-export of infrastructure classes. Remove, use direct imports.
- `models/ohlcv.py` — PURE. `Interval` enum + `OHLCV` model → deduplicate with `domain/ohlcv/`
- `models/quote.py` — PURE. `QuoteTick`, `AggregatedBar` → deduplicate with `domain/quote/`
- `models/symbol.py` — PURE. Symbol metadata → deduplicate with `domain/symbol/`
- `repositories/` — MongoDB persistence → `infrastructure/persistence/repositories/`
- **Most cross-referenced** module in codebase — backtesting, strategy, and trading all import market_data models

## Architecture

```
BEFORE:                                  AFTER:
features/market_data/                    features/market_data/
├── base/                                ├── router.py
│   ├── managers/                        ├── list_symbols/  {query, handler, route}
│   │   ├── bar_builder.py               ├── ohlcv/         {sub-router, get_ohlcv/}
│   │   └── bar_manager.py               ├── quotes/        {sub-router, 7 operations}
│   ├── models/                          ├── sync/          {sub-router, sync_one/, sync_bulk/}
│   │   ├── ohlcv.py                     └── status/        {sub-router, 3 operations}
│   │   ├── quote.py
│   │   └── symbol.py                   domain/ (extended)
│   ├── jobs/                            ├── ohlcv/value_objects.py   (+Interval, OHLCV)
│   │   └── sync_jobs.py                 ├── quote/value_objects.py   (+QuoteTick, AggregatedBar)
│   └── providers/                       └── symbol/value_objects.py  (+SymbolInfo updates)
│       └── __init__.py (re-export)
├── repositories/                        application/market_data/
│   └── ...                              ├── bar_manager.py
├── quotes/                              ├── quote_service.py
│   └── quote_service.py                 └── sync_jobs.py
├── router.py
└── ...14 operation dirs                 infrastructure/persistence/repositories/
                                         └── market_data/ (moved repos)
```

## Related Code Files

### Deduplicate models into domain (merge, not move)
- `src/features/market_data/base/models/ohlcv.py` → merge `Interval`, `OHLCV` into `src/domain/ohlcv/value_objects.py`
- `src/features/market_data/base/models/quote.py` → merge `QuoteTick`, `AggregatedBar`, `Quote` into `src/domain/quote/value_objects.py`
- `src/features/market_data/base/models/symbol.py` → merge into `src/domain/symbol/value_objects.py`

### Consolidate duplicate
- `src/features/market_data/base/managers/bar_builder.py` → DELETE (use existing `src/domain/ohlcv/services/bar_builder.py`)

### Move to application
- `src/features/market_data/base/managers/bar_manager.py` → `src/application/market_data/bar_manager.py`
- `src/features/market_data/base/jobs/sync_jobs.py` → `src/application/market_data/sync_jobs.py`
- `src/features/market_data/quotes/quote_service.py` → `src/application/market_data/quote_service.py`

### Move to infrastructure
- `src/features/market_data/repositories/*` → `src/infrastructure/persistence/repositories/market_data/`

### Delete
- `src/features/market_data/base/` (entire directory)
- `src/features/market_data/base/providers/__init__.py` (re-export, replace with direct imports)
- `src/features/market_data/repositories/` (after move)

### Modify (update imports — HIGH volume)
- All 14 operation handlers in market_data
- `src/application/backtesting/historical_replay_engine.py` (imports OHLCV model)
- `src/application/backtesting/backtest_runner.py` (imports market_data models)
- `src/application/market_data/bar_manager.py` (internal imports after move)
- `src/application/market_data/quote_service.py` (internal imports after move)
- DTOs: `src/features/market_data/ohlcv/dto.py`, `quotes/dto.py`, `sync/dto.py`, `status/dto.py`

## Implementation Steps

1. **Deduplicate models into domain (CRITICAL — most imports depend on these)**

   a. Read `src/domain/ohlcv/value_objects.py` — check what exists
   b. Read `src/features/market_data/base/models/ohlcv.py` — identify what's missing
   c. Merge `Interval` enum and `OHLCV` model into domain, avoiding duplicates
   d. Repeat for `quote.py` → `domain/quote/value_objects.py` (QuoteTick, AggregatedBar, Quote)
   e. Repeat for `symbol.py` → `domain/symbol/value_objects.py` (SymbolInfo, etc.)
   f. Update all `__init__.py` exports in domain packages

2. **Create import compatibility aliases (temporary)**
   - After merging, many files still import from `features.market_data.base.models`
   - Strategy: update imports directly (no aliases). Use `grep` to find ALL references.
   - `grep -r "features.market_data.base.models" src/` — list every file to update

3. **Consolidate bar_builder**
   - Compare `features/market_data/base/managers/bar_builder.py` with `domain/ohlcv/services/bar_builder.py`
   - If identical: delete features version, update imports to domain version
   - If different: merge any missing logic into domain version, then delete features version
   - Update `bar_manager.py` imports before moving it

4. **Move repositories to infrastructure**
   - Create `src/infrastructure/persistence/repositories/market_data/` with `__init__.py`
   - Move all repository files from `features/market_data/repositories/`
   - Update internal imports: models → domain value objects

5. **Move bar_manager to application**
   - Copy to `src/application/market_data/bar_manager.py`
   - Update imports:
     - `bar_builder` → `src.domain.ohlcv.services.bar_builder`
     - models → `src.domain.ohlcv.value_objects`, `src.domain.quote.value_objects`
     - Keep I/O imports (Cache, Database, logging) as-is

6. **Move quote_service to application**
   - Copy from `features/market_data/quotes/quote_service.py` → `src/application/market_data/quote_service.py`
   - Update imports:
     - `bar_manager` → `src.application.market_data.bar_manager`
     - providers → direct `src.infrastructure.tradingview` imports (remove re-export dependency)
     - models → domain value objects

7. **Move sync_jobs to application**
   - Copy to `src/application/market_data/sync_jobs.py`
   - Update imports: models → domain, mediator stays as-is

8. **Remove providers re-export**
   - Delete `features/market_data/base/providers/__init__.py`
   - Any file importing from it → change to `src.infrastructure.tradingview` directly

9. **Update ALL handler imports (14 handlers)**
   - For each handler in: list_symbols, ohlcv/get_ohlcv, quotes/* (7 ops), sync/* (2 ops), status/* (3 ops)
   - Replace: `src.features.market_data.base.models` → `src.domain.{ohlcv,quote,symbol}.value_objects`
   - Replace: `src.features.market_data.base.managers` → `src.application.market_data`
   - Replace: `src.features.market_data.repositories` → `src.infrastructure.persistence.repositories.market_data`
   - Replace: `src.features.market_data.quotes.quote_service` → `src.application.market_data.quote_service`

10. **Update cross-feature imports**
    - `src/application/backtesting/historical_replay_engine.py` — imports `OHLCV` model → domain
    - `src/application/backtesting/backtest_runner.py` — if it imports market_data models → domain
    - Any other file: `grep -r "features.market_data.base" src/` → must return zero

11. **Update DTOs (keep in features)**
    - `ohlcv/dto.py`, `quotes/dto.py`, `sync/dto.py`, `status/dto.py` — these may import base models
    - Update imports to domain value objects

12. **Delete `features/market_data/base/` and `features/market_data/repositories/`**

13. **Verify**
    - `grep -r "features.market_data.base" src/` → zero results
    - `grep -r "features.market_data.repositories" src/` → zero results
    - Domain purity: no I/O imports in domain/ohlcv/, domain/quote/, domain/symbol/
    - Run all market_data tests
    - Run backtesting tests (cross-dependency)

## Todo List
- [ ] Merge OHLCV models into domain/ohlcv/value_objects.py
- [ ] Merge Quote models into domain/quote/value_objects.py
- [ ] Merge Symbol models into domain/symbol/value_objects.py
- [ ] Consolidate bar_builder (eliminate duplicate)
- [ ] Move repositories to infrastructure/persistence/repositories/market_data/
- [ ] Move bar_manager to application/market_data/
- [ ] Move quote_service to application/market_data/
- [ ] Move sync_jobs to application/market_data/
- [ ] Remove providers re-export
- [ ] Update all 14 handler imports
- [ ] Update cross-feature imports (backtesting)
- [ ] Update DTOs
- [ ] Delete features/market_data/base/ and repositories/
- [ ] Verify: zero old references, domain purity, tests pass

## Success Criteria
- `features/market_data/` contains ONLY: router.py, sub-routers, operation dirs with DTOs
- No `base/` or `repositories/` in features/market_data/
- Domain models consolidated: single source of truth for OHLCV, Quote, Symbol
- bar_builder duplicate eliminated
- `application/market_data/` has bar_manager, quote_service, sync_jobs
- All tests pass (market_data + backtesting)

## Risk Assessment
- **HIGH: Mass import updates** — 14 handlers + cross-feature refs + DTOs. Most error-prone phase. Use systematic grep-and-replace.
- **HIGH: Model dedup conflicts** — Domain value_objects.py may define different versions of same types. Careful merge required — keep domain version as canonical, migrate any extra fields.
- **MEDIUM: bar_builder divergence** — The two copies may have drifted. Must compare carefully before deleting one.
- **LOW: Provider re-export removal** — Simple, just redirect imports.
