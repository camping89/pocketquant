# Phase 1: Create UUID Wrapper Module

## Overview
- **Priority:** P1
- **Status:** pending
- **Effort:** 20 minutes

Create centralized UUID generation module that wraps Python 3.14's native `uuid7()`.

## Key Insights

- Python 3.14 has native `uuid7()` in stdlib
- UUID v7 is time-ordered (first 48 bits = Unix timestamp ms)
- Drop-in replacement for uuid4 (same UUID type, same format)
- Wrapper enables future changes without touching every file

## Requirements

### Functional
- Single `generate_id() -> UUID` function
- Re-export `UUID` type for convenience
- Optional: `generate_id_str() -> str` for contexts needing string

### Non-Functional
- Zero external dependencies
- Type-safe with full annotations
- Simple, minimal implementation

## Architecture

```
src/common/
├── uuid.py          # NEW: UUID generation wrapper
└── ...
```

## Implementation

### Create `src/common/uuid.py`

```python
"""UUID generation utilities.

Uses Python 3.14's native uuid7() for time-ordered UUIDs.
Benefits: chronological sorting, better DB index performance.
"""

from uuid import UUID, uuid7

__all__ = ["UUID", "generate_id", "generate_id_str"]


def generate_id() -> UUID:
    """Generate a time-ordered UUID v7."""
    return uuid7()


def generate_id_str() -> str:
    """Generate a time-ordered UUID v7 as string."""
    return str(uuid7())
```

## Todo List

- [ ] Create `src/common/uuid.py` with generate_id functions
- [ ] Add exports to `src/common/__init__.py` if needed
- [ ] Verify import works: `from src.common.uuid import generate_id, UUID`

## Success Criteria

- Module creates valid UUID v7 values
- `generate_id()` returns `UUID` type
- `generate_id_str()` returns `str` type
- Import path works from any module

## Next Steps

Proceed to Phase 2: Migrate domain events
