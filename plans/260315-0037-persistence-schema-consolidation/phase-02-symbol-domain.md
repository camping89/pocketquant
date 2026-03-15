# Phase 2: Symbol Domain + Repo

## Overview
- **Priority**: HIGH
- **Status**: completed

## Context
- Current schema: `src/persistence/schemas/symbol_schema.py` — `SymbolBase`, `Symbol` (both Pydantic)
- Current aggregate: `src/domain/symbol/aggregate.py` — `SymbolAggregate` (dataclass)
- Current repo: `src/persistence/repositories/symbol_repository.py`
- `SymbolBase` used in: repo `upsert()`, handler `sync_one/handler.py`
- `Symbol` (child schema) — dead code, never used

## Files to Modify

| File | Action |
|------|--------|
| `src/domain/symbol/aggregate.py` | Migrate `SymbolAggregate` dataclass → Pydantic, add `to_mongo()`/`from_mongo()`, add `created_at` |
| `src/persistence/repositories/symbol_repository.py` | Use `SymbolAggregate.to_mongo()` / `from_mongo()`, remove `SymbolBase` import, remove `_doc_to_aggregate()` |
| `src/features/market_data/sync/sync_one/handler.py` | Replace `SymbolBase(...)` with `SymbolAggregate.create(...)` |
| `src/domain/symbol/__init__.py` | Update exports |

## Files to Delete
| File | Reason |
|------|--------|
| `src/persistence/schemas/symbol_schema.py` | Replaced by aggregate methods |

## Implementation Steps

### 1. Migrate `SymbolAggregate` (dataclass → Pydantic)

```python
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

class SymbolAggregate(BaseModel):
    """Aggregate root for symbol management."""
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    info: SymbolInfo | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SymbolAggregate):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    # ... existing methods stay (create, activate, deactivate, properties)
    # replace(self.info, ...) → self.info = self.info.model_copy(update={...})
    # BUT SymbolInfo is a frozen dataclass, so use dataclasses.replace() still

    def to_mongo(self) -> dict[str, Any]:
        return {
            "_id": str(self.id),
            "symbol": self.info.code.upper() if self.info else "",
            "exchange": self.info.exchange.upper() if self.info else "",
            "name": self.info.name if self.info else None,
            "asset_type": self.info.asset_type if self.info else None,
            "is_active": self.info.is_active if self.info else True,
            "created_at": self.created_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> "SymbolAggregate":
        info = SymbolInfo(
            code=doc.get("symbol", ""),
            exchange=doc.get("exchange", ""),
            name=doc.get("name"),
            asset_type=doc.get("asset_type"),
            is_active=doc.get("is_active", True),
        )
        raw_id = doc.get("_id", "")
        return cls(
            id=UUID(str(raw_id)) if raw_id else generate_id(),
            info=info,
            created_at=doc.get("created_at", _utc_now()),
        )
```

Note: `SymbolInfo` stays frozen dataclass (value object, not persisted). `replace()` calls in `activate()`/`deactivate()` still use `dataclasses.replace()`.

### 2. Update `SymbolRepository`

- Remove `from src.persistence.schemas.symbol_schema import SymbolBase`
- `upsert(symbol: SymbolAggregate)` — use `symbol.to_mongo()`, keep `$setOnInsert` for `created_at`, add `$set updated_at`
- `find_all()` — replace `_doc_to_aggregate(doc)` with `SymbolAggregate.from_mongo(doc)`
- Delete `_doc_to_aggregate()` helper

### 3. Update handler

- `sync_one/handler.py`: replace `SymbolBase(symbol=symbol, exchange=exchange)` with `SymbolAggregate.create(code=symbol, exchange=exchange)`

### 4. Delete `src/persistence/schemas/symbol_schema.py`

### 5. Compile check + test

## Success Criteria

- [x] `SymbolAggregate` is Pydantic with `to_mongo()`/`from_mongo()`
- [x] No imports from `src.persistence.schemas.symbol_schema` anywhere
- [x] `symbol_schema.py` deleted
- [x] `_id` is UUID7 string for all symbol docs
- [x] `created_at` on entity, `updated_at` repo-side
- [x] All tests pass
