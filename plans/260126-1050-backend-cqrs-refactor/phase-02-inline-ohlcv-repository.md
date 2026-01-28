# Phase 2: Inline OHLCV Repository

## Context
- [CQRS Research](./research/researcher-01-cqrs-patterns.md)
- Current: `OHLCVRepository` (222 LOC) called by DataSyncService, BarManager, sync_jobs
- Target: Direct DB access in services

## Overview
- **Priority:** P2
- **Status:** Pending
- **Effort:** 1.5 hr
- **Depends on:** Phase 1A, 1B, 1C completed

## Key Insights
- `OHLCVRepository` has 8 methods, 222 LOC
- Main callers: `DataSyncService`, `BarManager` (via upsert_many), `sync_jobs`
- Direct `Database.get_collection()` replaces repository layer

## Requirements

### Functional
- Inline all OHLCVRepository methods into calling services
- Maintain exact same DB operations and logging
- Keep sync_status operations in DataSyncService

### Non-functional
- Services < 200 LOC after changes (may need to split)
- No duplicate code across services

## Files

### Modify
- `src/features/market_data/services/data_sync_service.py`
- `src/features/market_data/managers/bar_manager.py`
- `src/features/market_data/jobs/sync_jobs.py`

### Delete (Phase 5)
- `src/features/market_data/repositories/ohlcv_repository.py`

## Method Migration Map

| Method | Current Caller | Move To |
|--------|---------------|---------|
| `upsert_many()` | DataSyncService, BarManager | DataSyncService (shared method) |
| `get_bars()` | DataSyncService | DataSyncService |
| `get_latest_bar()` | DataSyncService | DataSyncService |
| `get_bar_count()` | DataSyncService | DataSyncService |
| `update_sync_status()` | DataSyncService, sync_jobs | DataSyncService |
| `get_sync_status()` | routes.py | Keep in routes (Phase 3) |
| `get_all_sync_statuses()` | routes.py, sync_jobs | Keep in routes (Phase 3) |

## Implementation Steps

### Step 1: Add DB imports to DataSyncService
```python
from pymongo import UpdateOne
from src.common.database import Database
```

### Step 2: Add private DB helper methods to DataSyncService
```python
class DataSyncService:
    OHLCV_COLLECTION = "ohlcv"
    SYNC_STATUS_COLLECTION = "sync_status"

    async def _upsert_many(self, records: list[OHLCVCreate]) -> int:
        """Bulk upsert OHLCV records."""
        if not records:
            return 0

        collection = Database.get_collection(self.OHLCV_COLLECTION)
        operations = []

        for record in records:
            ohlcv = OHLCV(**record.model_dump())
            doc = ohlcv.to_mongo()
            created_at = doc.pop("created_at", None)

            update_ops: dict = {"$set": doc}
            if created_at:
                update_ops["$setOnInsert"] = {"created_at": created_at}

            operations.append(
                UpdateOne(
                    {
                        "symbol": doc["symbol"],
                        "exchange": doc["exchange"],
                        "interval": doc["interval"],
                        "datetime": doc["datetime"],
                    },
                    update_ops,
                    upsert=True,
                )
            )

        result = await collection.bulk_write(operations, ordered=False)
        return result.upserted_count + result.modified_count
```

### Step 3: Add sync status methods
```python
async def _update_sync_status(
    self,
    symbol: str,
    exchange: str,
    interval: Interval,
    status: str,
    bar_count: int | None = None,
    last_bar_at: datetime | None = None,
    error_message: str | None = None,
) -> None:
    collection = Database.get_collection(self.SYNC_STATUS_COLLECTION)
    # ... inline from OHLCVRepository.update_sync_status

async def _get_bar_count(self, symbol: str, exchange: str, interval: Interval) -> int:
    collection = Database.get_collection(self.OHLCV_COLLECTION)
    return await collection.count_documents({
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "interval": interval.value,
    })

async def _get_latest_bar(self, symbol: str, exchange: str, interval: Interval) -> OHLCV | None:
    collection = Database.get_collection(self.OHLCV_COLLECTION)
    doc = await collection.find_one(
        {"symbol": symbol.upper(), "exchange": exchange.upper(), "interval": interval.value},
        sort=[("datetime", -1)],
    )
    return OHLCV.from_mongo(doc) if doc else None
```

### Step 4: Update sync_symbol() to use private methods
Replace `OHLCVRepository.xxx()` calls with `self._xxx()` calls.

### Step 5: Update BarManager._save_completed_bar()
BarManager needs to save bars. Two options:
1. **Option A**: Import DataSyncService and call its upsert method
2. **Option B**: Inline the upsert logic in BarManager

**Choose Option B** (BarManager is pure domain, add minimal DB):
```python
# In BarManager._save_completed_bar()
from pymongo import UpdateOne
from src.common.database import Database

async def _save_completed_bar(self, bar: BarBuilder) -> None:
    if bar.is_empty():
        return
    # ... build OHLCVCreate
    collection = Database.get_collection("ohlcv")
    # ... inline single upsert
```

### Step 6: Update sync_jobs.py
Replace `OHLCVRepository.get_all_sync_statuses()` with direct DB query:
```python
async def _get_all_sync_statuses() -> list[SyncStatus]:
    collection = Database.get_collection("sync_status")
    cursor = collection.find()
    return [SyncStatus.from_mongo(doc) async for doc in cursor]
```

## Todo

- [ ] Add imports to DataSyncService
- [ ] Add `_upsert_many()` private method
- [ ] Add `_update_sync_status()` private method
- [ ] Add `_get_bar_count()`, `_get_latest_bar()` private methods
- [ ] Update `sync_symbol()` to use private methods
- [ ] Update BarManager `_save_completed_bar()` with inline upsert
- [ ] Update sync_jobs.py with inline sync status query
- [ ] Remove OHLCVRepository imports
- [ ] Run tests

## Success Criteria
- [ ] DataSyncService uses direct DB access
- [ ] BarManager saves bars with direct DB access
- [ ] sync_jobs uses direct DB access
- [ ] No imports from `repositories/ohlcv_repository`
- [ ] All tests pass
- [ ] Each file < 200 LOC

## Risks
- DataSyncService may exceed 200 LOC after inlining
- Mitigation: Split into `_db_helpers.py` if needed (extract private methods)
