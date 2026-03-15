# Phase 4: Position Domain + Repo

## Overview
- **Priority**: MEDIUM
- **Status**: completed

## Context
- Current schema: `src/persistence/schemas/position_schema.py` — `PositionDocument` (Pydantic)
- Current aggregate: `src/domain/position/aggregate.py` — `PositionAggregate` (dataclass)
- Current repo: `src/persistence/repositories/position_repository.py`

## Key Insight

`PositionAggregate` uses `opened_at` / `closed_at` as business timestamps — NOT generic `created_at` / `updated_at`. These stay on the entity. The repo will also `$set updated_at` as infrastructure timestamp.

`id` is already `str` (UUID7 string via `generate_id_str()`). No type change needed.

## Files to Modify

| File | Action |
|------|--------|
| `src/domain/position/aggregate.py` | Migrate dataclass → Pydantic, add `to_mongo()`/`from_mongo()` |
| `src/persistence/repositories/position_repository.py` | Use `position.to_mongo()` / `PositionAggregate.from_mongo()`, remove `PositionDocument` import |
| `src/domain/position/__init__.py` | Update exports |

## Files to Delete
| File | Reason |
|------|--------|
| `src/persistence/schemas/position_schema.py` | Replaced by aggregate methods |

## Implementation Steps

### 1. Migrate `PositionAggregate` (dataclass → Pydantic)

Same pattern as Order:
- `@dataclass` → `class PositionAggregate(BaseModel):`
- `_events` → `PrivateAttr(default_factory=list)`
- Add `to_mongo()` / `from_mongo()`

```python
def to_mongo(self) -> dict[str, Any]:
    return {
        "_id": self.id,
        "strategy_id": self.strategy_id,
        "symbol": self.symbol,
        "exchange": self.exchange,
        "side": self.side.value,
        "entry_price": self.entry_price,
        "quantity": self.quantity,
        "current_price": self.current_price,
        "realized_pnl": self.realized_pnl,
        "is_closed": self.is_closed,
        "opened_at": self.opened_at,
        "closed_at": self.closed_at,
    }

@classmethod
def from_mongo(cls, doc: dict[str, Any]) -> "PositionAggregate":
    return cls(
        id=doc["_id"],
        strategy_id=doc["strategy_id"],
        symbol=doc["symbol"],
        exchange=doc["exchange"],
        side=PositionSide(doc["side"]),
        entry_price=doc["entry_price"],
        quantity=doc["quantity"],
        current_price=doc["current_price"],
        realized_pnl=doc.get("realized_pnl", 0.0),
        is_closed=doc.get("is_closed", False),
        opened_at=doc["opened_at"],
        closed_at=doc.get("closed_at"),
    )
```

### 2. Update `PositionRepository`

Same pattern as Order — replace `PositionDocument.from_aggregate()` / `.to_aggregate()` with `position.to_mongo()` / `PositionAggregate.from_mongo(doc)`.

### 3. Delete `src/persistence/schemas/position_schema.py`

### 4. Compile check + test

## Success Criteria

- [x] `PositionAggregate` is Pydantic with `to_mongo()`/`from_mongo()`
- [x] No imports from `src.persistence.schemas.position_schema`
- [x] `position_schema.py` deleted
- [x] Business timestamps (`opened_at`, `closed_at`) preserved
- [x] All tests pass
