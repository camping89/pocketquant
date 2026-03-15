# Phase 4: Rename OHLCV → Bar

## Overview
- **Priority**: MEDIUM
- **Status**: pending

## Context

"OHLCV" is verbose. The entity is already called `Bar`. Align the entire subdomain: directory, repository, imports, constants.

Do this AFTER Phase 1 (delete OHLCVAggregate) — fewer files to rename.

## Renames

| From | To |
|------|----|
| `src/domain/ohlcv/` | `src/domain/bar/` |
| `src/domain/ohlcv/entities.py` | `src/domain/bar/entities.py` |
| `src/domain/ohlcv/ohlcv_event.py` | `src/domain/bar/bar_event.py` |
| `src/domain/ohlcv/services/bar_builder.py` | `src/domain/bar/services/bar_builder.py` |
| `src/domain/ohlcv/__init__.py` | `src/domain/bar/__init__.py` |
| `OHLCVRepository` class | `BarRepository` |
| `ohlcv_repository.py` | `bar_repository.py` |
| `build_ohlcv_cache_key()` | `build_bar_cache_key()` |
| `COLLECTION_OHLCV = "ohlcv"` | `COLLECTION_BARS = "bars"` |
| `CACHE_KEY_BAR_*` | Keep as-is (already "bar" named) |

## Files to Modify (import updates)

All files importing from `src.domain.ohlcv` or `OHLCVRepository`:
- `src/application/market_data/bar_app_service.py`
- `src/application/backtesting/historical_replay_app_service.py`
- `src/features/market_data/sync/sync_one/handler.py`
- `src/features/market_data/get_ohlcv/handler.py` (also rename handler?)
- `src/di/market_data.py`
- `src/di/persistence.py` (or wherever repos are wired)
- `src/common/constants.py` (cache key builder)
- Tests referencing OHLCV

## Implementation Steps

### 1. Rename directory

```bash
git mv src/domain/ohlcv src/domain/bar
```

### 2. Rename files within

```bash
git mv src/domain/bar/ohlcv_event.py src/domain/bar/bar_event.py
```

### 3. Rename `OHLCVRepository` → `BarRepository`

In `src/persistence/repositories/ohlcv_repository.py`:
- Rename class
- Rename file to `bar_repository.py`

### 4. Rename `build_ohlcv_cache_key` → `build_bar_cache_key`

In `src/common/constants.py`.

### 5. Update ALL imports across codebase

```bash
rg "from src.domain.ohlcv" src/
rg "OHLCVRepository" src/
rg "ohlcv_repository" src/
rg "build_ohlcv_cache_key" src/
```

### 6. Update `__init__.py` in new `src/domain/bar/`

### 7. Compile check + test

## Risk

- Broad rename — touches many files. Use `git mv` for clean history.
- Run full grep after to catch any stale references.

## Success Criteria

- [ ] `src/domain/ohlcv/` → `src/domain/bar/` directory renamed
- [ ] `OHLCVRepository` → `BarRepository` class renamed
- [ ] `ohlcv_event.py` → `bar_event.py` file renamed
- [ ] `build_ohlcv_cache_key` → `build_bar_cache_key` renamed
- [ ] Zero references to "ohlcv" in imports
- [ ] MongoDB collection renamed to `bars` (no prod data, safe to drop and rerun)
- [ ] All file/variable names use snake_case (not kebab-case)
- [ ] All tests pass
