# Phase 6: Remove dependency-injector from Project

**Priority:** Medium | **Status:** Pending | **Effort:** S

## Overview

Delete `src/container.py`, remove `dependency-injector` from deps, clean up any remaining references.

## Implementation Steps

1. Delete `src/container.py` (366 LOC)
2. Remove from `pyproject.toml`:
   ```
   # Remove this line from [project.dependencies]
   "dependency-injector>=4.41,<5",
   ```
3. Grep entire codebase for remaining references:
   ```
   grep -r "dependency_injector" src/
   grep -r "from src.container" src/
   grep -r "AppContainer" src/
   grep -r "resolve(" src/
   grep -r "app.state.container" src/
   ```
4. Fix any remaining imports found by grep
5. Run `pip install -e .` to verify no import errors

## Todo

- [ ] Delete `src/container.py`
- [ ] Remove `dependency-injector` from `pyproject.toml`
- [ ] Grep and fix all remaining references
- [ ] Reinstall project deps
- [ ] Run `pyright src/` — zero import errors
- [ ] Run `ruff check src/` — no lint issues

## Success Criteria

- `dependency-injector` not in installed packages
- Zero references to `container.py`, `AppContainer`, `resolve()`, `providers.*`
- Project installs and imports cleanly
