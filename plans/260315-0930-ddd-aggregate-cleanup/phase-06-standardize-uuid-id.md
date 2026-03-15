# Phase 6: Standardize UUID _id

## Overview
- **Priority**: MEDIUM
- **Status**: pending

## Context

Audit found inconsistent `_id` handling across MongoDB-persisted entities:
- `OrderAggregate`, `PositionAggregate`: have UUID `_id` ✓
- `SymbolAggregate`, `Bar`: have UUID `_id` but upsert by compound key ✓
- `SyncStatus`: NO `_id` field ✗

**Decision**: All entities get `_id: str = Field(default_factory=lambda: str(uuid4()))`. Repositories keep compound-key upserts where natural (time-series, reference data).

## Entities to Fix

| Entity | File | Current _id | Action |
|--------|------|-------------|--------|
| `SyncStatus` | `src/domain/ohlcv/entities.py` | None | Add UUID `_id` field, update `to_mongo()`/`from_mongo()` |

## Entities Already Correct (Verify Only)

| Entity | File | Status |
|--------|------|--------|
| `SymbolAggregate` | `src/domain/symbol/aggregate.py` | ✓ UUID _id |
| `Bar` | `src/domain/ohlcv/entities.py` | ✓ UUID _id |
| `OrderAggregate` | `src/domain/order/aggregate.py` | ✓ UUID _id |
| `PositionAggregate` | `src/domain/position/aggregate.py` | ✓ UUID _id |

## Implementation Steps

### 1. Add `_id` to `SyncStatus`

```python
class SyncStatus(BaseModel):
    _id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    exchange: str
    interval: str
    # ...

    def to_mongo(self) -> dict:
        doc = {
            "_id": self._id,
            "symbol": self.symbol,
            # ...
        }
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "SyncStatus":
        return cls(
            _id=str(doc.get("_id", "")),
            # ...
        )
```

### 2. Verify existing entities have consistent pattern

Quick check that all 5 entities follow the same `_id` pattern in `to_mongo()`/`from_mongo()`.

### 3. Handle existing MongoDB documents

Existing `SyncStatus` documents in MongoDB won't have our UUID `_id` — they'll have MongoDB's auto-generated ObjectId. The `from_mongo()` handles this with `str(doc.get("_id", ""))`, converting ObjectId to string. No migration needed.

### 4. Compile check + test

## Success Criteria

- [ ] `SyncStatus` has `_id: str` field
- [ ] `SyncStatus.to_mongo()` includes `_id`
- [ ] `SyncStatus.from_mongo()` reconstructs `_id`
- [ ] All 5 entities follow identical `_id` pattern
- [ ] Repository upsert patterns unchanged (compound keys preserved)
- [ ] All tests pass
