# Phase 2: Create New Repositories and Eliminate Raw DB Access

## Priority: P1 | Status: completed

## Overview
Create 4 missing repositories (OHLCV, SyncStatus, Symbol, Optimization), add a minimal base mixin, and replace all `Database.get_collection()` calls in handlers/application code with repository method calls.

## Context Links
- Existing repo pattern: `src/persistence/repositories/order_repository.py` (static methods, no base class)
- Heaviest raw-DB file: `src/features/market_data/sync/sync_one/handler.py` (5 get_collection calls)
- Constants: `src/common/constants.py` (COLLECTION_* names)

## Key Insights
- All existing repos use **static methods** + `Database.get_collection(COLLECTION_X)` pattern
- New repos should follow same pattern for consistency
- Base mixin is optional but useful to reduce `Database.get_collection(COLLECTION_X)` boilerplate inside repos
- The `_upsert_many` logic in sync_one/handler.py is complex (bulk_write) -- move verbatim to OHLCVRepository
- bar_manager.py has the same upsert logic -- both should call `OHLCVRepository.upsert_bar()`

## Files to CREATE

### `src/persistence/base_repository.py` (~15 lines)
Minimal mixin that provides `_collection()` shorthand:
```python
"""Base repository mixin for MongoDB collections."""
from src.persistence.mongodb import Database


class BaseRepository:
    """Mixin providing collection access. Subclasses set _collection_name."""
    _collection_name: str

    @classmethod
    def _collection(cls):
        return Database.get_collection(cls._collection_name)
```

### `src/persistence/repositories/ohlcv_repository.py` (~80 lines)
Extract from sync_one/handler.py and bar_manager.py:
```python
class OHLCVRepository(BaseRepository):
    _collection_name = COLLECTION_OHLCV

    @staticmethod async def upsert_many(records: list[OHLCVCreate]) -> int
    @staticmethod async def upsert_bar(ohlcv: OHLCV) -> None
    @staticmethod async def find(symbol, exchange, interval, start_date, end_date, limit) -> list[OHLCV]
    @staticmethod async def count(symbol, exchange, interval) -> int
    @staticmethod async def get_latest(symbol, exchange, interval) -> OHLCV | None
    @staticmethod async def ensure_indexes() -> None
```

Methods map to current inline code:
| Method | Currently in | Lines |
|--------|-------------|-------|
| `upsert_many` | sync_one/handler.py `_upsert_many()` | 142-181 |
| `upsert_bar` | bar_manager.py `_save_completed_bar()` | 84-114 |
| `find` | get_ohlcv/handler.py `_get_bars()` | 53-83 |
| `count` | sync_one/handler.py `_get_bar_count()` | 220-230 |
| `get_latest` | sync_one/handler.py `_get_latest_bar()` | 232-244 |
| `ensure_indexes` | NEW -- create compound index on (symbol, exchange, interval, datetime) |

### `src/persistence/repositories/sync_status_repository.py` (~50 lines)
Extract from sync_one/handler.py and sync_jobs.py:
```python
class SyncStatusRepository(BaseRepository):
    _collection_name = COLLECTION_SYNC_STATUS

    @staticmethod async def upsert(symbol, exchange, interval, status, **kwargs) -> None
    @staticmethod async def find_all() -> list[SyncStatus]
    @staticmethod async def find_one(symbol, exchange, interval) -> SyncStatus | None
    @staticmethod async def ensure_indexes() -> None
```

Methods map:
| Method | Currently in |
|--------|-------------|
| `upsert` | sync_one/handler.py `_update_sync_status()` lines 183-218 |
| `find_all` | sync_jobs.py `_get_all_sync_statuses()` + get_sync_status/handler.py |
| `find_one` | get_symbol_sync_status/handler.py lines 21-30 |

### `src/persistence/repositories/symbol_repository.py` (~40 lines)
Extract from sync_one/handler.py and list_symbols/handler.py:
```python
class SymbolRepository(BaseRepository):
    _collection_name = COLLECTION_SYMBOLS

    @staticmethod async def upsert(symbol, exchange) -> None
    @staticmethod async def find_all(exchange: str | None = None) -> list[dict]
    @staticmethod async def ensure_indexes() -> None
```

Methods map:
| Method | Currently in |
|--------|-------------|
| `upsert` | sync_one/handler.py `_upsert_symbol()` lines 246-258 |
| `find_all` | list_symbols/handler.py lines 13-31 |

### `src/persistence/repositories/optimization_repository.py` (~30 lines)
Extract from optimize/handler.py and get_optimization/handler.py:
```python
class OptimizationRepository(BaseRepository):
    _collection_name = COLLECTION_OPTIMIZATION_RUNS

    @staticmethod async def save(result: OptimizationResult) -> None
    @staticmethod async def get(optimization_id: str) -> OptimizationResult | None
    @staticmethod async def ensure_indexes() -> None
```

## Files to MODIFY

### Handlers -- replace raw DB calls with repository calls

**`src/features/market_data/sync/sync_one/handler.py`**
- Remove: `from src.common.database import Database`, collection constant imports for OHLCV/SYNC_STATUS/SYMBOLS
- Add: `from src.persistence.repositories.ohlcv_repository import OHLCVRepository`
- Add: `from src.persistence.repositories.sync_status_repository import SyncStatusRepository`
- Add: `from src.persistence.repositories.symbol_repository import SymbolRepository`
- Replace `_upsert_many()` body -> `return await OHLCVRepository.upsert_many(records)`
- Replace `_update_sync_status()` body -> `await SyncStatusRepository.upsert(...)`
- Replace `_get_bar_count()` -> `return await OHLCVRepository.count(...)`
- Replace `_get_latest_bar()` -> `return await OHLCVRepository.get_latest(...)`
- Replace `_upsert_symbol()` -> `await SymbolRepository.upsert(...)`

**`src/features/market_data/ohlcv/get_ohlcv/handler.py`**
- Remove: Database import, COLLECTION_OHLCV import
- Add: OHLCVRepository import
- Replace `_get_bars()` body -> `return await OHLCVRepository.find(...)`

**`src/features/market_data/list_symbols/handler.py`**
- Remove: Database import, COLLECTION_SYMBOLS import
- Add: SymbolRepository import
- Replace body -> `return await SymbolRepository.find_all(exchange=request.exchange)`

**`src/features/market_data/status/get_sync_status/handler.py`**
- Remove: Database import, COLLECTION_SYNC_STATUS import
- Add: SyncStatusRepository import
- Replace body -> `statuses = await SyncStatusRepository.find_all()`

**`src/features/market_data/status/get_symbol_sync_status/handler.py`**
- Remove: Database import, COLLECTION_SYNC_STATUS import
- Add: SyncStatusRepository import
- Replace body -> `status = await SyncStatusRepository.find_one(...)`

**`src/features/backtesting/optimize/handler.py`**
- Remove: Database import, COLLECTION_OPTIMIZATION_RUNS import
- Add: OptimizationRepository import
- Replace `_save_optimization_result()` -> `await OptimizationRepository.save(result)`

**`src/features/backtesting/get_optimization/handler.py`**
- Remove: Database import, COLLECTION_OPTIMIZATION_RUNS import
- Add: OptimizationRepository import
- Replace body -> `return await OptimizationRepository.get(request.optimization_id)`

**`src/application/market_data/bar_manager.py`**
- Remove: Database import, COLLECTION_OHLCV import
- Add: OHLCVRepository import
- Replace `_save_completed_bar()` body -> `await OHLCVRepository.upsert_bar(ohlcv)`

**`src/application/market_data/sync_jobs.py`**
- Remove: Database import, COLLECTION_SYNC_STATUS import
- Add: SyncStatusRepository import
- Replace `_get_all_sync_statuses()` -> `return await SyncStatusRepository.find_all()`

**`src/application/backtesting/backtest_runner.py`**
- Remove: Database import, COLLECTION_OHLCV import
- Add: OHLCVRepository import
- Replace `_load_bars()` -> use `OHLCVRepository.find()` or keep cursor-based streaming via new `OHLCVRepository.stream()` method

### Update existing repos to use BaseRepository

**`src/persistence/repositories/order_repository.py`**
- Add: `class OrderRepository(BaseRepository):` + `_collection_name = COLLECTION_ORDERS`
- Replace all `Database.get_collection(COLLECTION_ORDERS)` -> `cls._collection()`

**`src/persistence/repositories/position_repository.py`**
- Same pattern as order_repository

**`src/persistence/repositories/backtest_repository.py`**
- Same pattern as order_repository

### Update `src/main.py`
- Add index creation calls for new repos:
  ```python
  await OHLCVRepository.ensure_indexes()
  await SyncStatusRepository.ensure_indexes()
  await SymbolRepository.ensure_indexes()
  await OptimizationRepository.ensure_indexes()
  ```

### Update `src/persistence/repositories/__init__.py`
- Export all 7 repository classes for convenience

## Implementation Steps

1. Create `src/persistence/base_repository.py`
2. Create 4 new repository files with methods extracted from handlers
3. Update existing 3 repos to extend BaseRepository
4. Update `src/persistence/repositories/__init__.py` with all exports
5. Update each handler file (9 files) to use repository instead of raw DB
6. Update bar_manager.py and sync_jobs.py (2 application files)
7. Update backtest_runner.py to use OHLCVRepository
8. Add ensure_indexes() calls in main.py
9. Run `ruff check src/` -- no errors
10. Run `pytest` -- 60/60 pass

## Todo
- [ ] Create base_repository.py
- [ ] Create ohlcv_repository.py
- [ ] Create sync_status_repository.py
- [ ] Create symbol_repository.py
- [ ] Create optimization_repository.py
- [ ] Refactor existing repos to use BaseRepository
- [ ] Update sync_one/handler.py (biggest change -- 5 methods)
- [ ] Update get_ohlcv/handler.py
- [ ] Update list_symbols/handler.py
- [ ] Update get_sync_status/handler.py
- [ ] Update get_symbol_sync_status/handler.py
- [ ] Update optimize/handler.py
- [ ] Update get_optimization/handler.py
- [ ] Update bar_manager.py
- [ ] Update sync_jobs.py
- [ ] Update backtest_runner.py
- [ ] Update main.py with new ensure_indexes()
- [ ] Run tests -- 60/60 pass

## Success Criteria
- Zero `Database.get_collection()` calls outside `src/persistence/`
- All 7 repositories follow same BaseRepository pattern
- All handler files import from repos, never from Database directly
- 60/60 tests pass

## Risk
- backtest_runner._load_bars() uses async generator -- OHLCVRepository needs a `stream()` method that returns AsyncIterator, not a list. Watch for this.
- sync_one/handler.py is 259 lines and does a lot -- after extracting DB logic to repos it should shrink to ~150 lines

## Completion Status
Phase 2 complete. All 4 new repositories created (OHLCVRepository, SyncStatusRepository, SymbolRepository, OptimizationRepository). Existing 3 repos refactored to use BaseRepository. All 9 handlers updated to use repositories instead of raw DB calls. 60/60 tests passing.
