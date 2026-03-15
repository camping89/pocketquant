# Phase 3: Flatten SymbolAggregate → Symbol

## Overview
- **Priority**: MEDIUM
- **Status**: pending

## Context

`SymbolAggregate` is not an aggregate root — no child entities, no invariants to guard. It wraps `SymbolInfo` VO unnecessarily (over-engineering). Flatten to a single `Symbol` Pydantic entity with direct fields.

Also: dead event infra (`_events`, `get_uncommitted_events()`, `clear_events()`) — never used, no symbol domain events exist.

## Files to Modify

| File | Action |
|------|--------|
| `src/domain/symbol/aggregate.py` | Rewrite as `Symbol` entity: flatten `SymbolInfo` fields, remove event infra, keep `to_mongo()`/`from_mongo()`/`activate()`/`deactivate()` |
| `src/domain/symbol/__init__.py` | Update exports: `SymbolAggregate` → `Symbol` |
| `src/domain/symbol/value_objects.py` | Delete `SymbolInfo` if no longer used |
| All files importing `SymbolAggregate` | Update to `Symbol` |

## Files to Delete

| File | Reason |
|------|--------|
| `src/domain/symbol/value_objects.py` | `SymbolInfo` VO no longer needed (if only contains SymbolInfo) |

## Implementation Steps

### 1. Rewrite `aggregate.py` → rename to `entities.py`

```python
class Symbol(BaseModel):
    """Tradeable instrument — persisted to MongoDB."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    code: str = ""
    exchange: str = ""
    name: str | None = None
    asset_type: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=_utc_now)

    @classmethod
    def create(cls, code: str, exchange: str, name: str | None = None, asset_type: str | None = None) -> Symbol:
        return cls(code=code.upper(), exchange=exchange.upper(), name=name, asset_type=asset_type)

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

    def to_mongo(self) -> dict[str, Any]:
        return {
            "_id": str(self.id),
            "symbol": self.code,
            "exchange": self.exchange,
            "name": self.name,
            "asset_type": self.asset_type,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> Symbol:
        raw_id = doc.get("_id", "")
        return cls(
            id=UUID(str(raw_id)) if raw_id else generate_id(),
            code=doc.get("symbol", ""),
            exchange=doc.get("exchange", ""),
            name=doc.get("name"),
            asset_type=doc.get("asset_type"),
            is_active=doc.get("is_active", True),
            created_at=doc.get("created_at", _utc_now()),
        )
```

Note: `to_mongo()` keeps `"symbol"` as the MongoDB field name (not `"code"`) for backward compatibility with existing documents.

### 2. Delete old `aggregate.py`, create `entities.py`

### 3. Update `__init__.py`

Export `Symbol` instead of `SymbolAggregate`.

### 4. Delete `value_objects.py` (if only contains `SymbolInfo`)

Check if other VOs exist in the file first.

### 5. Update all imports

Find and replace `SymbolAggregate` → `Symbol` across codebase:
- Repository (`symbol_repository.py`)
- Handlers
- DI providers
- Tests

### 6. Compile check + test

## Migration Notes

- MongoDB field `"symbol"` stays as `"symbol"` in `to_mongo()` for collection field naming
- `symbol` property was `self.info.code` → now `self.code` directly
- All callers using `.symbol` property must update to `.code` — no alias, clean rename

## Success Criteria

- [ ] `SymbolAggregate` → `Symbol` (renamed class)
- [ ] `SymbolInfo` VO deleted
- [ ] Event infra removed (`_events`, `get_uncommitted_events`, `clear_events`, `DomainEvent` import)
- [ ] All imports updated across codebase
- [ ] File renamed: `aggregate.py` → `entities.py`
- [ ] MongoDB backward compatible (same field names in `to_mongo()`)
- [ ] All tests pass
