# Code Review: Clean Architecture Refactor

**Date:** 2026-02-14
**Branch:** `feat/strategy-init`
**Scope:** 411 files changed, ~25K insertions / ~24K deletions
**Focus:** Dependency direction, domain purity, import consistency, file placement, orphan cleanup

---

## Overall Assessment

The refactor is **well-executed**. The codebase now has a clear Clean Architecture layering:

```
Domain (pure) -> Application (orchestration) -> Features (thin CQRS) -> Infrastructure (I/O)
```

**Pyright: 0 errors, 0 warnings** across 290 source files.
**Tests: 60 passed, 0 failed.**
**Domain purity test: PASSED** (no I/O imports in `src/domain/`).

---

## Critical Issues

None found.

---

## High Priority

### H1. Application layer has direct `Database.get_collection` calls (architecture smell)

Three files in `src/application/` bypass the repository pattern and call `Database.get_collection()` directly:

| File | Line | Collection |
|------|------|-----------|
| `src/application/market_data/bar_manager.py` | 97 | `COLLECTION_OHLCV` |
| `src/application/market_data/sync_jobs.py` | 22 | `COLLECTION_SYNC_STATUS` |
| `src/application/backtesting/backtest_runner.py` | 154 | `COLLECTION_OHLCV` |

Additionally, `src/application/market_data/quote_service.py` and `bar_manager.py` call `Cache.set()`/`Cache.get()` directly.

**Impact:** Application layer couples to MongoDB/Redis internals. If persistence changes, application code must change too.

**Recommendation:** Extract these into infrastructure repositories (e.g., `OHLCVRepository.get_by_range()`, `SyncStatusRepository.get_all()`). Not blocking -- pragmatic for now since these are read-only queries with simple patterns, but should be addressed as the codebase grows.

### H2. `RiskCheckHandler` lives in features but is not a CQRS handler

`src/features/risk/check_risk/handler.py` contains `RiskCheckHandler` which is a synchronous validator, not a mediator command/query handler. It imports from `src.infrastructure.brokers` (AccountBalance).

**Current placement:** `src/features/risk/check_risk/handler.py`
**Better placement:** `src/application/risk/risk_validator.py` or `src/domain/risk/services/risk_validator.py`

It has no `@handles` decorator, is not registered with the mediator, and is instantiated directly in `main.py`. It's effectively a domain/application service masquerading as a feature handler.

**Impact:** Misleading architecture; new devs may assume it follows the CQRS handler pattern.

### H3. Domain purity test missing `src.application` and `src.features` guards

`tests/unit/domain/test_domain_purity.py` FORBIDDEN_IMPORTS list includes `src.infrastructure` but **not** `src.application` or `src.features`.

```python
# Current
FORBIDDEN_IMPORTS = [
    "pymongo", "redis", "aiohttp", "httpx",
    "src.infrastructure", "src.common.database",
    "src.common.cache", "src.common.jobs",
]

# Should also include:
"src.application",
"src.features",
"fastapi",
"structlog",  # domain should use plain logging or none
```

**Impact:** A future developer could accidentally import from application/features into domain and the test would not catch it.

---

## Medium Priority

### M1. Orphan directory: `src/features/market_data/repositories/`

This directory exists but contains only a `__pycache__` subfolder. No Python files. Appears to be a leftover from the refactor that moved repositories to `src/infrastructure/persistence/repositories/`.

**Fix:** Delete `src/features/market_data/repositories/` entirely (including its `__pycache__`).

### M2. `market_data/__init__.py` is still a thin stub

```python
"""Market data feature - OHLCV, quotes, sync, and status operations."""
```

All other feature modules have proper facade re-exports with `__all__`. Market data has no re-exports, making its public API unclear.

**Recommendation:** Either add facade re-exports (router, key handlers) or document why market_data intentionally opts out.

### M3. Feature `__init__.py` files re-export application layer types

`src/features/backtesting/__init__.py` re-exports `BacktestRunner`, `GridOptimizer`, `BacktestConfig`, `BacktestResult` from `src.application.backtesting.*`. Similarly for `trading` and `strategy`.

This creates a leaky abstraction where consumers can import application types through the feature facade. While convenient, it couples the public API to internal layer structure.

**Recommendation:** Accept this as pragmatic for now, but consider having feature facades only export DTOs, commands, queries, and routers. Application types should be imported directly by code that needs them.

### M4. Application `__init__.py` files are empty

All four application submodules have empty `__init__.py` files:
- `src/application/__init__.py`
- `src/application/market_data/__init__.py`
- `src/application/trading/__init__.py`
- `src/application/strategy/__init__.py`

Not a bug, but adding facade re-exports would make the application layer's public API explicit, matching the pattern used in features and domain.

### M5. Ruff linting: 42 issues (41 auto-fixable)

```
40x I001 unsorted-imports (auto-fixable)
 1x UP037 quoted-annotation (auto-fixable)
 1x UP046 non-pep695-generic-class
```

Also: `pyproject.toml` has deprecated top-level ruff config keys (should use `[tool.ruff.lint]` section).

**Fix:** Run `ruff check src/ --fix` and update pyproject.toml ruff config.

### M6. Feature handlers have direct `Database.get_collection` calls

Several feature handlers bypass repositories and directly access MongoDB:

- `src/features/market_data/sync/sync_one/handler.py` (5 calls)
- `src/features/market_data/list_symbols/handler.py`
- `src/features/market_data/ohlcv/get_ohlcv/handler.py`
- `src/features/market_data/status/get_sync_status/handler.py`
- `src/features/market_data/status/get_symbol_sync_status/handler.py`
- `src/features/backtesting/get_optimization/handler.py`
- `src/features/backtesting/optimize/handler.py`

These are query handlers that could use infrastructure repositories. Not blocking since the OHLCV/sync-status data doesn't have dedicated repositories yet, but it's inconsistent with the pattern used for orders/positions/backtests.

---

## Low Priority

### L1. Pytest collection warnings

Two test helper classes trigger `PytestCollectionWarning`:
- `tests/unit/common/test_event_bus.py:9` - `TestEvent`
- `tests/unit/common/test_mediator.py:15` - `TestCommand`

**Fix:** Rename to `SampleEvent`/`SampleCommand` or add `__test__ = False` attribute.

### L2. `_DefaultStrategy` inner class in strategy_engine.py

`src/application/strategy/strategy_engine.py` line 376 defines `_DefaultStrategy` as a module-level private class. This is fine but could live in `src/domain/strategy/strategies/` for consistency.

### L3. `console.print` hardcoded line reference in main.py

Line 149: `console.print("  -> [cyan]src/main.py:24[/] in lifespan")` -- this line reference is hardcoded and will go stale as the file changes.

---

## Dependency Direction Verification

### Allowed dependencies (PASS):

| Direction | Status |
|-----------|--------|
| Features -> Application | PASS (handlers import orchestrators) |
| Features -> Domain | PASS (handlers import value objects, events) |
| Features -> Infrastructure | PASS (only through facade/register files) |
| Application -> Domain | PASS (engines use domain types) |
| Application -> Infrastructure | PASS (uses repos, brokers, schemas) |
| Domain -> nothing external | PASS (only src.common utilities) |
| Infrastructure -> Domain | PASS (repos use domain aggregates) |

### Known accepted exceptions (verified):

| Exception | Location | Reason | Status |
|-----------|----------|--------|--------|
| `strategy_engine.py:18` | `from src.features.risk...` under TYPE_CHECKING | No runtime dep | VERIFIED |
| `sync_jobs.py:8` | `from src.features.market_data.sync` | Needs SyncSymbolCommand for mediator dispatch | VERIFIED |
| `backtest_repository.py:8` | `from src.application.backtesting.models` | Pydantic model reuse | VERIFIED |

### Reverse dependency violations: NONE detected

Infrastructure does not import from features. Domain does not import from application, infrastructure, or features.

---

## File Placement Verification

| Category | Expected Location | Actual | Status |
|----------|-------------------|--------|--------|
| MongoDB schemas | `infrastructure/persistence/schemas/` | 5 schema files present | PASS |
| Repositories | `infrastructure/persistence/repositories/` | 3 repos (backtest, order, position) | PASS |
| Engines/managers | `application/` | 7 files across 4 subdirs | PASS |
| Domain services | `domain/*/services/` | bar_builder, position_sizer, performance_calculator | PASS |
| Strategy interface | `domain/strategy/interfaces.py` | Present, pure ABC | PASS |
| Strategy implementations | `domain/strategy/strategies/` | ma_crossover.py | PASS |
| Feature `base/` dirs | Should not exist | None found | PASS |

---

## Positive Observations

1. **Zero type errors** across 290 files -- excellent type discipline
2. **Domain purity** is genuine -- no I/O, no framework dependencies in `src/domain/`
3. **`@handles` decorator** + `HandlerRegistry` auto-registration is clean and DRY
4. **Event handler auto-discovery** via `@event_handler` decorator + `EventRegistry` pattern
5. **Consistent operation structure**: every CQRS operation has `__init__.py`, `handler.py`, `command.py`/`query.py`, `route.py`
6. **Feature register.py** files provide clean DI composition roots
7. **TYPE_CHECKING guards** used properly to break circular dependencies
8. **Domain events** are well-structured (BarCompletedEvent, OrderFilledEvent, etc.)
9. **Good test for domain purity** exists (even if it needs a few more forbidden imports)
10. **All base/ directories removed** from features -- no orphan files

---

## Metrics

| Metric | Value |
|--------|-------|
| Pyright errors | 0 |
| Pyright warnings | 0 |
| Tests passing | 60/60 |
| Ruff issues | 42 (41 auto-fixable) |
| Domain purity | PASS |
| Dependency violations | 0 (3 accepted exceptions documented) |
| Orphan directories | 1 (`market_data/repositories/`) |

---

## Recommended Actions (Priority Order)

1. **Delete orphan** `src/features/market_data/repositories/` directory
2. **Add** `src.application`, `src.features`, `fastapi` to domain purity test FORBIDDEN_IMPORTS
3. **Run** `ruff check src/ --fix` to clear 41 auto-fixable issues
4. **Rename** test helper classes to avoid PytestCollectionWarning
5. **Move** `RiskCheckHandler` to application or domain layer (longer term)
6. **Extract** direct `Database.get_collection` calls from application layer into repositories (longer term)
7. **Add** `market_data/__init__.py` facade re-exports

---

## Unresolved Questions

1. Should `PerformanceCalculator` (domain) depend on `numpy`? It's a heavy dependency for the domain layer. Consider whether this qualifies as "pure" or if numpy is acceptable as a domain utility.
2. The `market_data` feature has no facade `__init__.py` re-exports -- is this intentional due to its size/complexity, or an oversight?
3. Should `sync_jobs.py` (application) use a module-global `_mediator` variable, or should it receive the mediator through DI? The current pattern uses a `set_mediator()` function which is a service locator anti-pattern.
