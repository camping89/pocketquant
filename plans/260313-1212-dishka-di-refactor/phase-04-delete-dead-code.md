# Phase 4: Delete Dead Code

## Context Links
- [Phase 3: Update Routes](./phase-03-update-routes.md) — must be complete first
- Files to delete: `src/services.py`, `src/dependencies.py`, `src/handler_registration.py`

## Overview
- **Priority**: P2
- **Status**: pending
- **Description**: Remove the 3 files that are now fully replaced by dishka providers. Verify no remaining imports.

## Files to Delete

| File | LOC | Replaced By |
|------|-----|-------------|
| `src/services.py` | 73 | Dishka container (providers resolve individual types) |
| `src/dependencies.py` | 31 | `FromDishka[]` in routes + `setup_dishka()` middleware |
| `src/handler_registration.py` | 118 | `register_handlers()` in `src/container.py` |

## Implementation Steps

### 1. Verify no remaining imports

```bash
rg "from src.services import" src/
rg "from src.dependencies import" src/
rg "from src.handler_registration import" src/
rg "src\.services" src/  # catch string references too
```

Expected: zero matches (all references removed in phases 2-3).

If matches remain:
- `src/main_extensions.py` might still import `Services` for type hints in helper functions
- Update those functions to take individual deps or container

### 2. Check for `app.state.services` references

```bash
rg "app\.state\.services" src/
```

Expected: zero matches. The health route and system/jobs route should now use `FromDishka[]`.

### 3. Delete files

```bash
git rm src/services.py
git rm src/dependencies.py
git rm src/handler_registration.py
```

### 4. Clean up `main_extensions.py`

Remove any remaining `from src.services import Services` and update type annotations.

### 5. Final verification

```bash
pyright src/
ruff check src/
uvicorn src.main:app  # smoke test
```

## Todo List

- [ ] Verify zero imports of deleted modules
- [ ] Verify zero `app.state.services` references
- [ ] Delete `src/services.py`
- [ ] Delete `src/dependencies.py`
- [ ] Delete `src/handler_registration.py`
- [ ] Clean up any remaining references in `src/main_extensions.py`
- [ ] Run `pyright src/` — zero errors
- [ ] Run `ruff check src/` — zero errors
- [ ] Start app — starts without import errors

## Success Criteria

- 3 files deleted, ~222 LOC removed
- No dangling imports
- App starts and all endpoints work
- Type checker passes

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Missed import causes ImportError at startup | App won't start | Run grep before deleting; smoke test after |
| Test files import from deleted modules | Tests break | Check in Phase 5 first, or search tests/ before deleting |
