# Phase 7: Ruff + Pyright

**Priority:** Medium | **Status:** Complete | **Effort:** 20m

## Overview

Run linters/type checker after all code changes to catch import errors, unused imports, and type issues introduced during migration.

## Depends On

- Phase 4 (pyrightconfig.json must be correct)
- All code-modifying phases (1-6) complete

## Implementation Steps

### Step 1: Ruff Fix + Format

```bash
ruff check --fix .
ruff format .
```

Expected issues:
- Unused imports in `__init__.py` files (from Phase 2 audit)
- Import sorting changes
- Minor formatting

Review all `--fix` changes before committing. Do NOT auto-fix `F401` (unused import) in `__init__.py` files -- those may be intentional re-exports.

### Step 2: Pyright Validation

```bash
pyright
```

Expected issues:
- Missing type stubs (should be `"none"` in config)
- Import errors if any old `src.*` references survived
- Type errors in handler files (pre-existing, not migration-related)

### Step 3: Triage Results

- **Fix:** Any `from src.` import errors (missed in Phase 4)
- **Fix:** Genuine type errors introduced by migration
- **Skip:** Pre-existing type warnings unrelated to migration
- **Log:** Pre-existing issues as tech debt (note in migration-doubts-and-notes.md if significant)

## Success Criteria

- [x] `ruff check .` passes with 0 errors
- [x] `ruff format --check .` passes (no unformatted files)
- [x] `pyright` has no new errors from migration (pre-existing OK)
- [x] No `from src.` or `import src.` anywhere in codebase
