# Phase 6: Validation & Cleanup

## Context

- Parent: [plan.md](plan.md)
- Depends on: Phases 1-5

## Overview

- **Priority:** P1 (gate)
- **Status:** pending
- **Effort:** 15m

Validate all changes, run tests, cleanup obsolete code.

## Validation Steps

### 1. Remove Domain Purity Test

The domain purity test checked for forbidden imports (pydantic) in domain layer.
Now that we use Pydantic everywhere, remove or update this test.

```bash
# Find and remove/update
rm tests/unit/domain/test_domain_purity.py
# OR update to check for other patterns
```

### 2. Type Checking

```bash
pyright src/
```

All should pass with no errors.

### 3. Run Tests

```bash
pytest tests/ -v
```

Update any failing tests due to:
- dataclass → Pydantic constructor changes
- model_dump() instead of asdict()
- PrivateAttr access patterns

### 4. OpenAPI Verification

```bash
python -m src.main
# Open http://localhost:8765/api/v1/docs
```

Verify all endpoints show correct schemas.

### 5. Cleanup

- Remove unused dataclass imports
- Remove obsolete `to_dict()` methods (use model_dump())
- Remove obsolete `from_dict()` methods (use model_validate())

## Todo

- [ ] Remove/update test_domain_purity.py
- [ ] Run pyright on entire src/
- [ ] Fix any type errors
- [ ] Run pytest
- [ ] Fix any failing tests
- [ ] Verify OpenAPI docs
- [ ] Remove unused imports
- [ ] Commit changes

## Common Migration Issues

| Issue | Fix |
|-------|-----|
| `asdict()` not found | Use `model_dump()` |
| Constructor kwargs | Pydantic accepts same kwargs |
| Frozen mutation | Check for accidental mutations |
| PrivateAttr access | Access via `obj._events` not `obj.events` |
| Validator errors | Update `__post_init__` to `@field_validator` |

## Success Criteria

- [ ] pyright passes with no errors
- [ ] All tests pass
- [ ] OpenAPI docs correct
- [ ] No dataclass imports remaining (except where justified)
- [ ] Clean git diff (no debug code)
