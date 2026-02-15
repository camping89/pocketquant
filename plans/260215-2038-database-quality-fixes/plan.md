---
status: completed
priority: high
branch: feat/strategy-init
---

# Database Quality Fixes

Consolidated fixes from code review. No new files unless stated.

## Phase 1: Schema & Domain Entity Returns

### 1.1 SymbolRepository — return `Symbol` domain entity
- `src/persistence/repositories/symbol_repository.py`
- `find_all()` returns `list[dict]` → change to `list[Symbol]` using `Symbol.from_mongo(doc)`
- `upsert()` accepts individual params → accept `SymbolCreate` schema object instead
- Add `.upper()` normalization for `symbol` and `exchange` inside repo
- Update callers in handlers to work with `Symbol` objects

### 1.2 SyncStatusRepository — return `SyncStatus` domain entity
- `src/persistence/repositories/sync_status_repository.py`
- `upsert()` builds doc manually → use `SyncStatus` schema with `to_mongo()` for validation
- `find_all()` already returns `SyncStatus` ✓
- Ensure all methods return domain objects, not raw dicts

## Phase 2: Data Integrity

### 2.1 OHLCV unique compound index
- `src/persistence/repositories/ohlcv_repository.py` — `ensure_indexes()`
- Add `unique=True` to `(symbol, exchange, interval, datetime)` compound index

### 2.2 UUID7 for all collections
- `src/persistence/schemas/ohlcv_schema.py` — generate UUID7 `_id` on write instead of relying on MongoDB ObjectId
- `src/persistence/schemas/symbol_schema.py` — same
- Update `to_mongo()`/`from_mongo()` for both schemas
- Keep existing `_id` handling backward-compatible (read both ObjectId and UUID7 strings)

### 2.3 BulkWriteError handling
- `src/persistence/repositories/ohlcv_repository.py` — `upsert_many()`
- Wrap `bulk_write()` in `try/except BulkWriteError` — log partial failure details (count of failed ops, error codes) then re-raise so callers know sync was partial

## Phase 3: Query Safety

### 3.1 Add limits to unbounded queries
- `order_repository.py` — `find_by_strategy()` add `limit=1000` default param
- `order_repository.py` — `find_pending()` add `limit=500` default param
- `position_repository.py` — `find_open()` add `limit=200` default param

### 3.2 Cursor cleanup in stream()
- `ohlcv_repository.py` — `stream()` wrap in `try/finally` with `await cursor.close()`

### 3.3 Remove redundant Interval conversion in stream()
- `ohlcv_repository.py` — remove inline `isinstance` check, let `from_mongo()` handle it

## Phase 4: Cache

### 4.1 Consistent cache key builder
- `src/common/constants.py` (or similar) — add a `build_ohlcv_cache_key(symbol, exchange, interval)` function
- Replace all hardcoded `f"ohlcv:{symbol}:{exchange}:{interval.value}"` strings with this function
- Used by: `get_ohlcv/handler.py`, `sync_one/handler.py`, `bar_manager.py`

### 4.2 BarManager cache invalidation
- `src/application/market_data/bar_manager.py` — `_save_completed_bar()`
- BarManager already has `cache` injected (via container)
- After `upsert_bar()`, call `cache.delete_pattern(f"{build_ohlcv_cache_key(...)}:*")`

### 4.3 Redis MGET for GetAllQuotesHandler
- `src/persistence/redis.py` — add `mget(keys: list[str])` method to `Cache` class
- `src/features/market_data/quotes/get_all/handler.py` — replace serial `cache.get()` loop with single `cache.mget(keys)` call

## Phase 5: Index

### 5.1 Backtest metric sort index
- `src/persistence/repositories/backtest_repository.py` — `ensure_indexes()`
- Add compound indexes for commonly used metrics: `(strategy_id, metrics.sortino_ratio)`, `(strategy_id, metrics.win_rate)`

## Separate Plan (Future)

### OrderManager/PositionTracker in-memory cache management
- Add LRU eviction or periodic cleanup (keep only recent days)
- On cache miss, fall back to MongoDB query
- When order/position data changes, mark cache stale and refresh
- **Not in this plan** — needs its own design since it touches core trading state

## Files Changed

| File | Changes |
|---|---|
| `symbol_repository.py` | Return `Symbol`, accept `SymbolCreate`, uppercase normalization |
| `sync_status_repository.py` | Use `SyncStatus` schema for writes |
| `ohlcv_repository.py` | Unique index, UUID7, BulkWriteError, cursor cleanup, remove redundant conversion |
| `ohlcv_schema.py` | UUID7 _id generation |
| `symbol_schema.py` | UUID7 _id generation |
| `order_repository.py` | Add default limits |
| `position_repository.py` | Add default limit |
| `backtest_repository.py` | Add metric indexes |
| `bar_manager.py` | Cache invalidation after bar save |
| `redis.py` | Add `mget()` method |
| `get_all/handler.py` | Use `mget()` |
| `common/constants.py` | Add `build_ohlcv_cache_key()` |
| `get_ohlcv/handler.py` | Use cache key builder |
| `sync_one/handler.py` | Use cache key builder |
| Handlers consuming Symbol/SyncStatus | Adapt to domain entity returns |

## Verify
- [ ] Run linting/type check
- [ ] Run tests
