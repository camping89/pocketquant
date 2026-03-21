# Brainstorm: Post-Migration Monorepo Cleanup

**Date:** 2026-03-21 | **Status:** Agreed — plan next

## Problem
Monolith→monorepo migration left broken configs, stale files, dead plans. 6 files completely broken (Dockerfile, launch.json, settings.json, pyrightconfig, check_env.py, justfile).

## Agreed Actions (dependency order)

### Phase 1: Delete dead files
- `repomix-output.xml`, `testscripts/__pycache__/`
- Plans: `260321-1849-migration-doubts-cleanup/`, `260321-0902-monorepo-package-split/` + reports

### Phase 2: TOML + `__init__.py` audit
- Root pyproject.toml correct. Verify package tomls. Audit 97 init files for stale re-exports.

### Phase 3: Move files
- `http/` → `tests/http/`
- `testscripts/` → `tests/manual/`
- `scripts/{cleanup.sh,server-setup.sh}` → `docker/scripts/`

### Phase 4: Fix broken configs
- `check_env.py`: `from src.config` → `from pocketquant.core.config`
- `pyrightconfig.json`: include packages paths
- `.vscode/settings.json`: remove stale extraPaths
- `.vscode/launch.json`: fix entrypoint
- `justfile`: `uv sync`, remove dead ref, add workspace commands

### Phase 5: Dockerfile rewrite
- Monorepo-aware multi-stage build

### Phase 6: Update docs
- README.md simplified + monorepo structure
- justfile expanded
- TODO.md rewritten (~20 lines)
- Optional: .vscode/tasks.json

### Phase 7: Ruff + Pyright
- `ruff check --fix . && ruff format .`
- `pyright` validation

### Phase 8: Docker compose check
- Verify compose.prod.yml app service config

## Decisions
- http/ → tests/http/ (Bruno collection)
- testscripts/ → tests/manual/
- ops scripts → docker/scripts/
- Delete both completed plans + reports
- Dockerfile included in this cleanup
- TODO.md: rewrite, keep actionable items only
