# Phase 6: Non-Persisted Aggregates + Cleanup

## Overview
- **Priority**: LOW
- **Status**: completed

## Context
- `OHLCVAggregate` — not directly persisted, transient aggregate for events
- `src/persistence/schemas/__init__.py` — empty barrel, directory may be removable
- Previous plan `260309-0918` — mark as superseded

## Scope

### Migrate `OHLCVAggregate` (dataclass → Pydantic)

```python
class OHLCVAggregate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    symbol: str = ""
    exchange: str = ""
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    # ... existing methods stay (create, record_sync, record_bar_completed)
```

No `to_mongo()`/`from_mongo()` — not persisted.

### Cleanup `src/persistence/schemas/`

After phases 1-5, this directory should only contain `__init__.py` (empty). Delete the directory if nothing imports from it.

### Verify no stale imports

```bash
rg "from src.persistence.schemas" src/
```

Should return zero matches.

### Update `src/domain/__init__.py` barrel exports

Ensure all migrated entities/aggregates are properly exported.

### Mark previous plan superseded

Update `plans/260309-0918-domain-pydantic-to-dataclass-refactor/plan.md` frontmatter:
```yaml
status: superseded
superseded_by: [260315-0037-persistence-schema-consolidation]
```

### Full test suite

```bash
ruff check src/ && pyright src/ && pytest
```

## Files to Modify

| File | Action |
|------|--------|
| `src/domain/ohlcv/aggregate.py` | Migrate dataclass → Pydantic |
| `src/domain/ohlcv/__init__.py` | Update exports |
| `src/domain/__init__.py` | Verify exports |
| `plans/260309-0918.../plan.md` | Mark superseded |

## Files to Delete

| File | Reason |
|------|--------|
| `src/persistence/schemas/__init__.py` | Empty, no consumers |
| `src/persistence/schemas/` (directory) | All contents deleted in prior phases |

## Success Criteria

- [x] All domain entities/aggregates are Pydantic BaseModel
- [x] `src/persistence/schemas/` directory deleted
- [x] Zero imports from `src.persistence.schemas` in codebase
- [x] All tests pass
- [x] `ruff check` + `pyright` clean
- [x] Previous plan marked superseded
