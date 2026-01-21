# Phase 3: Update Repository Type Hints

## Context Links
- [Plan Overview](plan.md)
- [Phase 2: Database Connection](phase-02-migrate-database-connection.md)
- [ohlcv_repository.py](../../src/features/market_data/repositories/ohlcv_repository.py)
- [symbol_repository.py](../../src/features/market_data/repositories/symbol_repository.py)

## Overview
- **Priority:** P2 (required for type safety)
- **Status:** pending
- **Effort:** 20m
- **Description:** Update repository files to use PyMongo Async type hints instead of Motor types

## Key Insights
- Repositories use Motor types only for type hints (return types)
- Actual operations (`find`, `bulk_write`, etc.) are identical between Motor and PyMongo Async
- `async for doc in cursor` pattern already correct (no `.each()` used)
- No `to_list(0)` patterns found (no changes needed)

## Requirements

### Functional
- Type hints accurate for `_get_collection()` methods
- All repository operations continue working

### Non-Functional
- mypy type checking passes
- IDE autocompletion works correctly

## Architecture
Simple type hint replacement. No behavioral changes.

```python
# Motor
from motor.motor_asyncio import AsyncIOMotorCollection

# PyMongo Async
from pymongo.asynchronous.collection import AsyncCollection
```

## Related Code Files

### Files to Modify

#### 1. ohlcv_repository.py
| Line | Current | New |
|------|---------|-----|
| 5 | `from motor.motor_asyncio import AsyncIOMotorCollection` | `from pymongo.asynchronous.collection import AsyncCollection` |
| 27 | `def _get_collection(cls) -> AsyncIOMotorCollection:` | `def _get_collection(cls) -> AsyncCollection:` |
| 32 | `def _get_sync_collection(cls) -> AsyncIOMotorCollection:` | `def _get_sync_collection(cls) -> AsyncCollection:` |

#### 2. symbol_repository.py
| Line | Current | New |
|------|---------|-----|
| 5 | `from motor.motor_asyncio import AsyncIOMotorCollection` | `from pymongo.asynchronous.collection import AsyncCollection` |
| 20 | `def _get_collection(cls) -> AsyncIOMotorCollection:` | `def _get_collection(cls) -> AsyncCollection:` |

## Implementation Steps

### Step 1: Update ohlcv_repository.py

**Line 5 - Import:**
```python
# BEFORE
from motor.motor_asyncio import AsyncIOMotorCollection

# AFTER
from pymongo.asynchronous.collection import AsyncCollection
```

**Line 27 - _get_collection return type:**
```python
# BEFORE
@classmethod
def _get_collection(cls) -> AsyncIOMotorCollection:
    """Get the OHLCV collection."""
    return Database.get_collection(cls.COLLECTION_NAME)

# AFTER
@classmethod
def _get_collection(cls) -> AsyncCollection:
    """Get the OHLCV collection."""
    return Database.get_collection(cls.COLLECTION_NAME)
```

**Line 32 - _get_sync_collection return type:**
```python
# BEFORE
@classmethod
def _get_sync_collection(cls) -> AsyncIOMotorCollection:
    """Get the sync status collection."""
    return Database.get_collection(cls.SYNC_STATUS_COLLECTION)

# AFTER
@classmethod
def _get_sync_collection(cls) -> AsyncCollection:
    """Get the sync status collection."""
    return Database.get_collection(cls.SYNC_STATUS_COLLECTION)
```

### Step 2: Update symbol_repository.py

**Line 5 - Import:**
```python
# BEFORE
from motor.motor_asyncio import AsyncIOMotorCollection

# AFTER
from pymongo.asynchronous.collection import AsyncCollection
```

**Line 20 - _get_collection return type:**
```python
# BEFORE
@classmethod
def _get_collection(cls) -> AsyncIOMotorCollection:
    """Get the symbols collection."""
    return Database.get_collection(cls.COLLECTION_NAME)

# AFTER
@classmethod
def _get_collection(cls) -> AsyncCollection:
    """Get the symbols collection."""
    return Database.get_collection(cls.COLLECTION_NAME)
```

## Verification Checklist

Operations verified compatible (no changes needed):
- [x] `find()` - Same API
- [x] `find_one()` - Same API
- [x] `bulk_write()` - Same API
- [x] `update_one()` - Same API
- [x] `count_documents()` - Same API
- [x] `delete_one()` - Same API
- [x] `async for doc in cursor` - Same pattern
- [x] `.sort()` - Same API
- [x] `.limit()` - Same API

## Todo List
- [ ] Update ohlcv_repository.py import (line 5)
- [ ] Update ohlcv_repository.py _get_collection return type (line 27)
- [ ] Update ohlcv_repository.py _get_sync_collection return type (line 32)
- [ ] Update symbol_repository.py import (line 5)
- [ ] Update symbol_repository.py _get_collection return type (line 20)
- [ ] Verify no other Motor imports in codebase: `grep -r "motor" src/`

## Success Criteria
- No `motor` imports anywhere in `src/` directory
- `mypy src/` passes (or only unrelated errors)
- Repository methods continue to work (tested in Phase 6)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Generic type parameter needed | Low | Low | Add `[dict]` if mypy complains: `AsyncCollection[dict]` |
| Hidden Motor imports | Low | Medium | Run grep to find all Motor references |
| Cursor behavior change | Very Low | High | Already using `async for` pattern |

## Security Considerations
- No security impact (type hint changes only)
- No runtime behavior changes

## Next Steps
After completion, proceed to [Phase 4: Update Configuration](phase-04-update-configuration.md)
