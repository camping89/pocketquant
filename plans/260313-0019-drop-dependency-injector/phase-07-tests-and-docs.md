# Phase 7: Update Tests and Documentation

**Priority:** Medium | **Status:** Pending | **Effort:** M

## Overview

Update test fixtures, fix broken test imports, and update all docs that reference `dependency-injector` / `AppContainer` / IoC container pattern.

## Context Links

- Test fixtures: `tests/conftest.py`
- Docs: `docs/code-standards.md`, `docs/system-architecture.md`, `docs/codebase-summary.md`

## Implementation Steps

### Tests

1. Update `tests/conftest.py` — tests already create instances directly (no container), so minimal changes expected
2. Grep for container references in tests:
   ```
   grep -r "AppContainer\|from src.container\|resolve(" tests/
   ```
3. Fix any broken imports
4. Run full test suite: `pytest`

### Documentation Updates

5. **`docs/code-standards.md`** — Section "3. Dependency Injection Container (IoC Pattern)":
   - Replace IoC Container description with Services registry pattern
   - Update code examples to show `Services` dataclass + `Depends()`
   - Remove `providers.Singleton/Resource/Factory` references
   - Update "Deprecated Patterns" section

6. **`docs/system-architecture.md`** — Section "Dependency Injection (IoC Container)":
   - Replace provider types table with Services pattern
   - Update startup sequence to show explicit init
   - Update resource lifecycle section

7. **`docs/codebase-summary.md`**:
   - Remove `dependency-injector` from Dependencies list
   - Update "Architecture" description: remove "IoC Container"
   - Update container references in module breakdown

### Memory Update

8. Update memory file for DI pattern decision (current memory references `dependency-injector`)

## Key Doc Changes

**Before (code-standards.md):**
```
Architecture: Clean Architecture + DDD + CQRS + IoC Container
- dependency-injector — IoC container
- providers.Singleton, providers.Resource, providers.Factory
```

**After:**
```
Architecture: Clean Architecture + DDD + CQRS
- Services dataclass — typed service registry
- FastAPI Depends() — route-level injection
- Explicit constructors — handler wiring
```

## Todo

- [ ] Grep tests for container references, fix any
- [ ] Run `pytest` — all tests pass
- [ ] Update `docs/code-standards.md` — DI section
- [ ] Update `docs/system-architecture.md` — DI + lifecycle sections
- [ ] Update `docs/codebase-summary.md` — deps + architecture description
- [ ] Update memory file for new DI convention
- [ ] Run `ruff check` and `pyright` one final time

## Success Criteria

- All tests pass
- Docs accurately describe new Services + Depends() pattern
- No mention of `dependency-injector` in docs (except maybe changelog)
- Memory updated for future conversations
