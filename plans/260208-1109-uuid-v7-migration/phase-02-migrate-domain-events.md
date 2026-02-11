# Phase 2: Migrate Domain Events

## Overview
- **Priority:** P1
- **Status:** pending
- **Effort:** 30 minutes

Migrate `DomainEvent` base class from `uuid4()` to `generate_id()`.

## Key Insights

- `DomainEvent` is the base for ALL domain events
- Single change propagates to all event types
- Uses Pydantic `Field(default_factory=...)` pattern

## Related Files

| File | Current Code | Change |
|------|-------------|--------|
| `src/domain/shared/domain_event.py` | `from uuid import UUID, uuid4` | `from src.common.uuid import UUID, generate_id` |

## Current Implementation

```python
# src/domain/shared/domain_event.py (current)
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DomainEvent(BaseModel):
    """Base class for all domain events."""

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

## Target Implementation

```python
# src/domain/shared/domain_event.py (after)
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.common.uuid import UUID, generate_id


class DomainEvent(BaseModel):
    """Base class for all domain events."""

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=generate_id)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DomainEvent):
            return NotImplemented
        return self.event_id == other.event_id

    def __hash__(self) -> int:
        return hash(self.event_id)
```

## Implementation Steps

1. Update import: `from uuid import UUID, uuid4` → `from src.common.uuid import UUID, generate_id`
2. Update Field: `default_factory=uuid4` → `default_factory=generate_id`
3. Run type check: `pyright src/domain/shared/domain_event.py`

## Todo List

- [ ] Update imports in `domain_event.py`
- [ ] Replace `uuid4` with `generate_id` in Field default_factory
- [ ] Verify type checking passes
- [ ] Run tests for domain events

## Success Criteria

- `DomainEvent` creates UUID v7 event IDs
- All event subclasses work without modification
- Type checking passes

## Next Steps

Proceed to Phase 3: Migrate aggregates and entities
