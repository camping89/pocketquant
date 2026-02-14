# Code Review: Persistence Layer Refactor

**Date:** 2026-02-14
**Reviewer:** code-reviewer agent
**Branch:** feat/strategy-init (unstaged changes)

---

## Scope

- **New files:** 13 files in `src/persistence/` (835 LOC total)
- **Modified files:** ~30 files across features/, application/, common/, infrastructure/
- **Deleted files:** All contents of `src/infrastructure/persistence/` (moved to `src/persistence/`)
- **Focus:** Persistence extraction, BaseRepository pattern, dependency direction

## Overall Assessment

**PASS** -- This is a well-executed structural refactor. The extraction of `src/persistence/` as a top-level package is clean, consistent, and correctly eliminates all `Database.get_collection()` calls from handlers and application code. All 60 tests pass, pyright reports 0 errors, ruff reports 0 issues on the new code.

The refactor resolves two major known issues from prior review:
1. Application layer direct `Database.get_collection` calls (bar_manager, sync_jobs, backtest_runner)
2. Feature handlers with direct DB access (market_data handlers)

---

## Critical Issues

None.

---

## High Priority

### H1. `datetime.utcnow()` deprecation in schemas (pre-existing, now consolidated)

**Files:**
- `src/persistence/schemas/ohlcv_schema.py:29` -- `created_at: dt = Field(default_factory=dt.utcnow)`
- `src/persistence/schemas/quote_schema.py:12` -- `timestamp: dt = Field(default_factory=dt.utcnow)`

`datetime.utcnow()` is deprecated since Python 3.12 and returns a naive datetime. The codebase already uses `datetime.now(UTC)` everywhere else (see `symbol_schema.py:7-9` for the correct pattern with `_utc_now()`).

**Fix:** Replace with timezone-aware factory:
```python
from datetime import UTC, datetime
created_at: dt = Field(default_factory=lambda: datetime.now(UTC))
```

### H2. `pymongo.UpdateOne` import outside persistence boundary

**File:** `src/persistence/repositories/ohlcv_repository.py:6`

```python
from pymongo import UpdateOne
```

This is acceptable since `OHLCVRepository` *is* inside `src/persistence/`. Noting for completeness: pymongo imports are now correctly confined to only `src/persistence/mongodb.py` and `src/persistence/repositories/ohlcv_repository.py`. The redis import is only in `src/persistence/redis.py`. The dependency boundary is clean.

**Verdict:** Not an issue -- correctly scoped.

---

## Medium Priority

### M1. BaseRepository is a mixin but uses class-level state

**File:** `src/persistence/base_repository.py`

```python
class BaseRepository:
    """Mixin providing collection access. Subclasses set _collection_name."""
    _collection_name: str

    @classmethod
    def _collection(cls):
        return Database.get_collection(cls._collection_name)
```

The `_collection()` method has no return type annotation. Adding it improves IDE support:

```python
from pymongo.asynchronous.collection import AsyncCollection

@classmethod
def _collection(cls) -> AsyncCollection:
    return Database.get_collection(cls._collection_name)
```

This is minor since pyright already resolves the type via inference (0 errors), but explicit typing is better for documentation.

### M2. All repository methods are `@staticmethod` with explicit class name

Every repository method calls `ClassName._collection()` explicitly:
```python
@staticmethod
async def find(symbol: str, ...) -> list[OHLCV]:
    collection = OHLCVRepository._collection()  # Explicit class name
```

This works but is slightly fragile if a subclass were created. Since the design uses composition (no inheritance between repos), this is acceptable. Using `@classmethod` with `cls._collection()` would be more idiomatic but would require changing every method signature. Not blocking.

### M3. `ohlcv_repository.py` at 184 lines -- approaching 200-line limit

Per project rules, files should stay under 200 lines. This file is the largest repository at 184 lines. The methods are well-organized and cohesive, so no split needed now, but watch this file if more query methods are added.

### M4. `ensure_indexes()` called eagerly in `main.py` for all 7 repos

**File:** `src/main.py:60-66`

```python
await OrderRepository.ensure_indexes()
await PositionRepository.ensure_indexes()
await BacktestRepository.ensure_indexes()
await OHLCVRepository.ensure_indexes()
await SyncStatusRepository.ensure_indexes()
await SymbolRepository.ensure_indexes()
await OptimizationRepository.ensure_indexes()
```

These are called sequentially. For startup performance, consider `asyncio.gather()`:
```python
await asyncio.gather(
    OrderRepository.ensure_indexes(),
    PositionRepository.ensure_indexes(),
    BacktestRepository.ensure_indexes(),
    OHLCVRepository.ensure_indexes(),
    SyncStatusRepository.ensure_indexes(),
    SymbolRepository.ensure_indexes(),
    OptimizationRepository.ensure_indexes(),
)
```

Low impact since indexes are idempotent and fast on existing collections, but cleaner.

### M5. `src/common/database/__init__.py` and `src/common/cache/__init__.py` are now just re-export shims

```python
# src/common/database/__init__.py
from src.persistence import Database, get_database
```

```python
# src/common/cache/__init__.py
from src.persistence import Cache, get_cache
```

These exist so that `main.py` can still do `from src.common.database import Database`. This is fine for backward compatibility, but consider whether to migrate callers directly to `from src.persistence import Database` and remove the shims. The `src/common/health/checks.py` already imports from `src.persistence` directly. Inconsistent but not breaking.

---

## Low Priority

### L1. `src/infrastructure/__init__.py` re-exports `Database` and `Cache` from `src.persistence`

```python
from src.persistence import Cache, Database
```

This creates a third import path for the same classes (`src.persistence`, `src.common.database`, `src.infrastructure`). Consider cleaning up to a single canonical import path.

### L2. Docstring says "re-exports from infrastructure" in common modules

```python
# src/common/database/__init__.py
"""MongoDB database module - re-exports from infrastructure."""
```

Should now say "re-exports from persistence" since the source moved.

### L3. `SyncStatusRepository.upsert()` duplicates `.upper()` calls

**File:** `src/persistence/repositories/sync_status_repository.py:29-31`

```python
update_doc: dict = {
    "symbol": symbol.upper(),
    "exchange": exchange.upper(),
```

And the filter also does `.upper()`:
```python
await collection.update_one(
    {
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
```

The caller (`SyncSymbolHandler.handle`) already uppercases on line 30-31. Double `.upper()` is harmless but noisy.

---

## Edge Cases Found by Scout

### E1. `OHLCVRepository.find()` returns empty `datetime` subdoc when neither start_date nor end_date

**File:** `src/persistence/repositories/ohlcv_repository.py:105-106`

```python
if start_date or end_date:
    query["datetime"] = {}
    if start_date:
        query["datetime"]["$gte"] = start_date
    if end_date:
        query["datetime"]["$lte"] = end_date
```

If `start_date` is falsy but `end_date` is provided (or vice versa), this works correctly because only one condition is added. However, if both are `None`, the condition `start_date or end_date` is `False`, so nothing is added. Correct behavior.

BUT: if `start_date` is `datetime(1970, 1, 1)` (epoch), it's truthy, which is also correct. No issue found.

### E2. `OHLCVRepository.stream()` takes `interval: str` but `find()` takes `interval: Interval`

**Inconsistency:**
- `stream(interval: str)` -- raw string
- `find(interval: Interval)` -- enum
- `count(interval: Interval)` -- enum
- `get_latest(interval: Interval)` -- enum

The `stream()` method on line 124 takes `interval: str` while all other methods take `Interval` enum. This inconsistency could lead to bugs if callers pass the wrong type. The method also manually converts `str` to `Interval` on line 142:

```python
if isinstance(doc.get("interval"), str):
    doc["interval"] = Interval(doc["interval"])
```

**Recommendation:** Change `stream()` parameter to `interval: Interval` and use `interval.value` in the query, matching the other methods.

### E3. No `SyncStatus` schema used by `SymbolRepository`

`SymbolRepository.find_all()` returns raw `list[dict]` rather than a typed `Symbol` model. The `symbol_schema.py` has a `Symbol` class, but it's unused by the repository. This was likely intentional for simplicity, but breaks the pattern of other repos that use typed schemas.

---

## Dependency Direction Verification

**PASS** -- Dependency rules are correctly enforced:

| Layer | Imports from `src.persistence` | Verdict |
|-------|-------------------------------|---------|
| `src/domain/` | None | PASS |
| `src/features/` | Repositories + schemas | PASS (expected) |
| `src/application/` | Repositories + schemas | PASS (expected) |
| `src/infrastructure/` | Schemas only (tradingview) + re-exports | PASS |
| `src/common/` | Re-export shims + health checks | PASS |
| `src/persistence/` | `src.common`, `src.domain`, `src.application` (optimization_repository) | See below |

**One notable dependency:** `src/persistence/repositories/optimization_repository.py:3` imports from `src.application`:
```python
from src.application.backtesting.models.optimization_result import OptimizationResult
```

This creates a `persistence -> application` dependency, which is an upward dependency violation. Similarly, `backtest_repository.py:5` imports:
```python
from src.application.backtesting.models.backtest_result import BacktestResult
```

These are the same accepted exceptions from the prior review (models that should arguably live in domain). Documenting for traceability.

---

## Positive Observations

1. **Single responsibility achieved** -- `Database.get_collection()` is now called exactly once, in `BaseRepository._collection()`. All 7 repos inherit this cleanly.
2. **pymongo/redis imports fully contained** -- Only 3 files import pymongo, only 1 imports redis, all within `src/persistence/`.
3. **Pattern consistency** -- All repos follow identical structure: `_collection_name`, `@staticmethod` methods, `_collection()` calls.
4. **Zero type errors** -- pyright 0 errors across entire `src/`.
5. **Zero lint issues** -- ruff clean on `src/persistence/`.
6. **Tests stable** -- 60/60 passing, no regressions.
7. **Index management centralized** -- Each repo owns its `ensure_indexes()`, called at startup in `main.py`.
8. **No behavior changes** -- Compared handler diffs; DB logic was extracted without modification.

---

## Metrics

| Metric | Value |
|--------|-------|
| Pyright errors | 0 |
| Ruff issues | 0 |
| Test results | 60/60 passing |
| New files | 13 |
| New LOC | 835 |
| Deleted files | ~8 (infrastructure/persistence/*) |

---

## Recommended Actions

1. **[High]** Fix `dt.utcnow` deprecation in `ohlcv_schema.py:29` and `quote_schema.py:12`
2. **[Medium]** Add return type annotation to `BaseRepository._collection()` -> `AsyncCollection`
3. **[Medium]** Make `OHLCVRepository.stream()` take `interval: Interval` instead of `str` for consistency
4. **[Medium]** Consider `asyncio.gather()` for parallel index creation in `main.py`
5. **[Low]** Update docstrings in `src/common/database/__init__.py` and `src/common/cache/__init__.py`
6. **[Low]** Standardize import paths -- choose one canonical path for `Database`/`Cache`

---

## Unresolved Questions

1. Should `BacktestResult` and `OptimizationResult` models move to `src/domain/` to eliminate the `persistence -> application` dependency? This was flagged in the prior review but not yet resolved.
2. Should `SymbolRepository.find_all()` return `list[Symbol]` instead of `list[dict]` for consistency with other repos?
3. Are the `src/common/database` and `src/common/cache` re-export shims intended to be permanent, or transitional?
