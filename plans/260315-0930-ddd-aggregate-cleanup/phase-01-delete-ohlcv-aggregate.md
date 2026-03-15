# Phase 1: Delete OHLCVAggregate + HistoricalDataSyncedEvent

## Overview
- **Priority**: HIGH
- **Status**: pending

## Context
- `src/domain/ohlcv/aggregate.py` — `OHLCVAggregate` (Pydantic, in-memory only)
- Used ONCE in `src/features/market_data/sync/sync_one/handler.py` line 156
- Guards no invariants, owns no entities, just wraps event creation
- `HistoricalDataSyncedEvent` has ZERO subscribers — dead event (YAGNI: delete)

## Files to Modify

| File | Action |
|------|--------|
| `src/features/market_data/sync/sync_one/handler.py` | Remove OHLCVAggregate usage + HistoricalDataSyncedEvent publishing entirely |
| `src/domain/ohlcv/__init__.py` | Remove `OHLCVAggregate` and `HistoricalDataSyncedEvent` exports |

## Files to Delete

| File | Reason |
|------|--------|
| `src/domain/ohlcv/aggregate.py` | Dead aggregate |

## Implementation Steps

### 1. Update sync handler (`handler.py`)

Remove `_publish_sync_event()` method entirely (lines ~148-162) and its call site. No replacement needed — event has zero subscribers.

Remove imports:
- `from src.domain.ohlcv import OHLCVAggregate`
- Any import of `HistoricalDataSyncedEvent`

### 2. Comment out `HistoricalDataSyncedEvent` in `ohlcv_event.py`

Comment the class with a note: placeholder for future use (UI sync notifications). Keep `BarCompletedEvent` (used by Phase 5).

### 3. Update `src/domain/ohlcv/__init__.py`

Remove `OHLCVAggregate` from imports and `__all__`. Remove `HistoricalDataSyncedEvent` export (commented out in event file).

### 4. Delete `src/domain/ohlcv/aggregate.py`

### 5. Verify no other references
```bash
rg "OHLCVAggregate|HistoricalDataSyncedEvent" src/
```

### 6. Compile check + test

## Success Criteria

- [ ] `OHLCVAggregate` class deleted
- [ ] `HistoricalDataSyncedEvent` commented out with placeholder note
- [ ] No imports referencing either anywhere
- [ ] Sync handler no longer publishes dead event
- [ ] All tests pass
