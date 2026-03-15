# Phase 3: Clean SymbolAggregate

## Overview
- **Priority**: LOW
- **Status**: pending

## Context
- `src/domain/symbol/aggregate.py` — `SymbolAggregate` (Pydantic, persisted)
- Has real behavior: `create()`, `activate()`, `deactivate()`, `to_mongo()`/`from_mongo()`
- `_events: list[DomainEvent] = PrivateAttr(default_factory=list)` — **never used**
- `get_uncommitted_events()` / `clear_events()` — **never called**
- No symbol domain events exist

## Files to Modify

| File | Action |
|------|--------|
| `src/domain/symbol/aggregate.py` | Remove `_events` PrivateAttr, `get_uncommitted_events()`, `clear_events()`, `DomainEvent` import |

## Implementation Steps

### 1. Remove dead event infrastructure from `SymbolAggregate`

Remove:
```python
from src.domain.shared.domain_event import DomainEvent
```

Remove:
```python
_events: list[DomainEvent] = PrivateAttr(default_factory=list)
```

Remove:
```python
def get_uncommitted_events(self) -> list[DomainEvent]:
    return self._events.copy()

def clear_events(self) -> None:
    self._events.clear()
```

Also remove `PrivateAttr` from pydantic import if no longer needed.

### 2. Compile check + test

## Success Criteria

- [ ] No `_events` on `SymbolAggregate`
- [ ] No `DomainEvent` import in symbol aggregate
- [ ] `activate()`/`deactivate()`/`to_mongo()`/`from_mongo()` still work
- [ ] All tests pass
