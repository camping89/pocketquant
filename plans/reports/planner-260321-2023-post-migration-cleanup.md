# Planner Report: Post-Migration Monorepo Cleanup

**Date:** 2026-03-21 | **Plan:** `plans/260321-2023-post-migration-cleanup/`

## Summary

Created 8-phase cleanup plan for post-monolith-to-monorepo migration. All broken configs identified, exact fixes specified with before/after content. Total estimated effort: ~3h.

## Key Findings During Research

1. **`pocketquant.api.main:run` is broken** -- `[project.scripts]` in api pyproject.toml references a `run()` function that does not exist in `main.py`. Plan recommends adding a 3-line `run()` function (Phase 4).

2. **compose.prod.yml is already correct** -- uses pre-built ghcr.io image with port 41920. Only needs syntax validation after Dockerfile rewrite.

3. **~90 `__init__.py` files** across packages. Most are empty namespace markers (fine). Audit needed for stale re-exports (Phase 2).

4. **`repomix-output.xml` already in .gitignore** -- just needs disk deletion.

## Phase Dependency Graph

```
Phase 1 (delete) ─────┐
Phase 2 (toml audit) ──┼── Phase 4 (fix configs) ── Phase 7 (ruff+pyright)
Phase 3 (move files) ──┘          │
                          Phase 5 (dockerfile) ── Phase 8 (compose check)
                          Phase 6 (update docs) ──┘
```

Phases 1-3 can run in parallel. Phase 4 depends on 2+3. Phases 5+6 depend on 4. Phase 7 runs after all code changes. Phase 8 last.

## Files in Plan

| File | Description |
|------|-------------|
| `plan.md` | Overview, phase table, dependency graph |
| `phase-01-delete-dead-files.md` | Delete 2 plan dirs, 4 reports, repomix XML, pycache |
| `phase-02-toml-init-audit.md` | Verify 4 package tomls + audit init files for stale imports |
| `phase-03-move-files.md` | http/ -> tests/http/, testscripts/ -> tests/manual/, ops -> docker/scripts/ |
| `phase-04-fix-broken-configs.md` | Fix all 6 broken configs with exact before/after content |
| `phase-05-dockerfile-rewrite.md` | Full Dockerfile rewrite for uv workspace monorepo |
| `phase-06-update-docs.md` | README.md rewrite, migration-doubts cleanup |
| `phase-07-ruff-pyright.md` | Lint + type check after all changes |
| `phase-08-docker-compose-check.md` | Validate compose files against new Dockerfile |

## Unresolved Questions

None -- all decisions were made in the brainstorm. Plan is ready for implementation.

**Status:** DONE
**Summary:** 8-phase cleanup plan created with exact file changes, dependency order, and success criteria.
