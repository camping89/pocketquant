# Phase 2: TOML + `__init__.py` Audit

**Priority:** High | **Status:** Complete | **Effort:** 20m

## Overview

Verify all 4 package pyproject.toml files have correct build config. Audit ~90 `__init__.py` files for stale re-exports referencing old `src.*` paths.

## Context

- Namespace packages: no `__init__.py` at `pocketquant/` level (PEP 420)
- Each package uses hatchling with `packages = ["src/pocketquant"]`
- Root `pyproject.toml` is correct (workspace config only)

## Files to Read

- `packages/pocketquant-core/pyproject.toml`
- `packages/pocketquant-backtest/pyproject.toml`
- `packages/pocketquant-trading/pyproject.toml`
- `packages/pocketquant-api/pyproject.toml`
- All `__init__.py` files under `packages/*/src/`

## Implementation Steps

### TOML Audit

1. Verify each package pyproject.toml has:
   - Correct `[tool.hatch.build.targets.wheel]` with `packages = ["src/pocketquant"]`
   - Correct `[tool.uv.sources]` referencing workspace deps
   - No stale `src.*` references in scripts/entrypoints
2. **Known issue:** `pocketquant-api/pyproject.toml` has `[project.scripts] pocketquant = "pocketquant.api.main:run"` but `run()` does not exist. Either add the function or remove the entry. (Fixed in Phase 4.)

### `__init__.py` Audit

3. Grep all `__init__.py` files for:
   - `from src.` or `import src.` (old monolith imports)
   - Stale re-exports that reference moved modules
4. Check for empty `__init__.py` files that exist only as namespace markers -- these are fine, leave them
5. Verify no `__init__.py` exists at bare `pocketquant/` level in any package (namespace package requirement)

### Verification Commands

```bash
# Check for old src imports in any init file
grep -r "from src\.\|import src\." packages/*/src/pocketquant/**/__init__.py

# Check no __init__.py at pocketquant/ namespace level
ls packages/*/src/pocketquant/__init__.py 2>/dev/null  # should find nothing
```

## Success Criteria

- [x] All 4 package pyproject.toml files have correct build config
- [x] No `__init__.py` contains `from src.` or `import src.`
- [x] No `__init__.py` at `pocketquant/` namespace level
- [x] Stale re-exports identified and logged (fix in Phase 4 or 7)
