# Phase 1: Delete OHLCVAggregate

## Overview
- **Priority**: HIGH
- **Status**: pending

## Context
- `src/domain/ohlcv/aggregate.py` — `OHLCVAggregate` (Pydantic, in-memory only)
- Used ONCE in `src/features/market_data/sync/sync_one/handler.py` line 156
- Guards no invariants, owns no entities, just wraps event creation
- `record_bar_completed()` method never called anywhere

## Files to Modify

| File | Action |
|------|--------|
| `src/features/market_data/sync/sync_one/handler.py` | Inline `HistoricalDataSyncedEvent` creation, remove `OHLCVAggregate` import |
| `src/domain/ohlcv/__init__.py` | Remove `OHLCVAggregate` export |
| `src/domain/__init__.py` | Check if `OHLCVAggregate` is exported (it's not currently) |

## Files to Delete

| File | Reason |
|------|--------|
| `src/domain/ohlcv/aggregate.py` | Dead aggregate, replaced by inline event creation |

## Implementation Steps

### 1. Update sync handler

Replace:
```python
aggregate = OHLCVAggregate(symbol=symbol, exchange=exchange)
aggregate.record_sync(
    interval=DomainInterval(interval.value),
    bars_count=bars_count,
    last_bar_at=latest_bar.datetime if latest_bar else datetime.now(UTC),
)
await self.event_bus.publish_all(aggregate.get_uncommitted_events())
```

With:
```python
event = HistoricalDataSyncedEvent(
    symbol=symbol,
    exchange=exchange,
    interval=interval.value,
    bars_count=bars_count,
    last_bar_at=latest_bar.datetime if latest_bar else datetime.now(UTC),
)
await self.event_bus.publish(event)
```

### 2. Update imports in handler
- Remove `from src.domain.ohlcv import OHLCVAggregate`
- Add `from src.domain.ohlcv.ohlcv_event import HistoricalDataSyncedEvent`

### 3. Update `src/domain/ohlcv/__init__.py`
- Remove `OHLCVAggregate` from imports and `__all__`

### 4. Check EventBus API
- Verify `event_bus.publish(event)` exists (single event) vs `publish_all(events)` (list)
- If only `publish_all` exists, wrap: `await self.event_bus.publish_all([event])`

### 5. Delete `src/domain/ohlcv/aggregate.py`

### 6. Verify no other references
```bash
rg "OHLCVAggregate" src/
```

### 7. Compile check + test

## Success Criteria

- [ ] `OHLCVAggregate` class deleted
- [ ] No imports from `src.domain.ohlcv.aggregate` anywhere
- [ ] `HistoricalDataSyncedEvent` created inline in handler
- [ ] All tests pass
