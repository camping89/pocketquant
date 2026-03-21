---
title: "Post-Migration Monorepo Cleanup"
description: "Fix broken configs, delete stale files, rewrite Dockerfile for 4-package uv workspace"
status: completed
priority: P1
effort: 3h
branch: feat/strategy-init
tags: [cleanup, monorepo, config, docker]
created: 2026-03-21
---

# Post-Migration Monorepo Cleanup

Monolith-to-monorepo migration left 6+ broken configs, stale plan files, misplaced scripts, and a Dockerfile that copies `src/`. This plan fixes everything in 8 lean phases.

## Monorepo Context

```
packages/
  pocketquant-core/       # 0 deps
  pocketquant-backtest/   # -> core
  pocketquant-trading/    # -> core
  pocketquant-api/        # -> core + backtest + trading (composition root)
```

- Entrypoint: `pocketquant.api.main:app` (FastAPI instance via `create_app()`)
- CLI script: `pocketquant.api.main:run` (defined in api pyproject.toml but **function does not exist** -- must be added or entry removed)
- Install: `uv sync` (workspace root)
- Run: `uvicorn pocketquant.api.main:app`

## Phases

| # | Phase | Effort | Status |
|---|-------|--------|--------|
| 1 | [Delete dead files](phase-01-delete-dead-files.md) | 10m | Complete |
| 2 | [TOML + __init__.py audit](phase-02-toml-init-audit.md) | 20m | Complete |
| 3 | [Move misplaced files](phase-03-move-files.md) | 15m | Complete |
| 4 | [Fix broken configs](phase-04-fix-broken-configs.md) | 30m | Complete |
| 5 | [Dockerfile rewrite](phase-05-dockerfile-rewrite.md) | 30m | Complete |
| 6 | [Update docs](phase-06-update-docs.md) | 30m | Complete |
| 7 | [Ruff + Pyright](phase-07-ruff-pyright.md) | 20m | Complete |
| 8 | [Docker compose check](phase-08-docker-compose-check.md) | 15m | Complete |

## Dependencies

- Phase 2 before 4 (init audit may reveal import issues configs depend on)
- Phase 3 before 4 (justfile refs scripts that move)
- Phase 4 before 7 (pyright config must be correct before running pyright)
- Phase 5 before 8 (Dockerfile needed for compose.prod.yml validation)
- Phase 7 after all code changes (phases 1-6)

## Key Discovery During Research

- `pyproject.toml` `[project.scripts]` entry `pocketquant = "pocketquant.api.main:run"` is broken -- no `run()` function exists in `main.py`. Fix in Phase 4.
- `repomix-output.xml` already in `.gitignore` but file exists on disk.
- `testscripts/__pycache__/` tracked despite `.gitignore` pattern (likely added before ignore rule).
