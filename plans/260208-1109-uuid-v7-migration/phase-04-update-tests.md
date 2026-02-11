# Phase 4: Update Tests & Verify

## Overview
- **Priority:** P1
- **Status:** pending
- **Effort:** 30 minutes

Update any test files using uuid4 and verify entire migration works.

## Key Insights

- Tests may import `uuid4` directly for test data
- UUID v7 is valid UUID - existing assertions still work
- Focus on import updates, not logic changes

## Test Files to Check

Search for `uuid4` in test files:

```bash
grep -r "uuid4" tests/
```

Common patterns to update:
- `from uuid import uuid4` → `from src.common.uuid import generate_id`
- Test fixtures creating UUIDs
- Mock/patch of uuid functions

## Verification Steps

### 1. Run Type Checking

```bash
pyright src/
```

Expected: No type errors related to UUID.

### 2. Run Linting

```bash
ruff check .
```

Expected: No unused imports of `uuid4`.

### 3. Run Full Test Suite

```bash
pytest -v
```

Expected: All tests pass.

### 4. Verify UUID v7 Generation

Quick verification script:

```python
from src.common.uuid import generate_id

# Generate a few IDs
ids = [generate_id() for _ in range(5)]

# Verify they're time-ordered (version 7)
for uid in ids:
    print(f"{uid} - version: {uid.version}")
    assert uid.version == 7

# Verify chronological ordering
timestamps = [uid.time for uid in ids]  # uuid7 has .time attribute
assert timestamps == sorted(timestamps)
print("All UUIDs are valid v7 and time-ordered!")
```

## Cleanup Checklist

- [ ] Remove any unused `from uuid import uuid4` imports
- [ ] Verify no `uuid4` references remain in src/
- [ ] Verify tests don't break due to UUID format assumptions
- [ ] Update any documentation mentioning uuid4

## Search Commands

```bash
# Find remaining uuid4 references
grep -r "uuid4" src/ --include="*.py"

# Should return empty after migration

# Verify new imports
grep -r "from src.common.uuid import" src/ --include="*.py"

# Should show all migrated files
```

## Todo List

- [ ] Search for uuid4 usage in tests
- [ ] Update test file imports if needed
- [ ] Run pyright on entire codebase
- [ ] Run ruff check
- [ ] Run full test suite
- [ ] Verify no uuid4 imports remain in src/
- [ ] Manual test: create aggregate, verify ID is v7

## Success Criteria

- Zero `uuid4` imports in `src/` directory
- All type checks pass
- All tests pass
- Generated UUIDs are version 7

## Final Verification

```bash
# Complete verification sequence
ruff check . && pyright src/ && pytest -v

# Verify no uuid4 remains
grep -r "uuid4" src/ --include="*.py" | wc -l
# Expected: 0
```

## Rollback Plan

If issues arise:
1. Revert changes to individual files
2. Remove `src/common/uuid.py`
3. Original uuid4 behavior restored

Low risk: UUID v7 is drop-in compatible with UUID v4.
