---
phase: 2
title: "Validate"
status: completed
priority: P2
effort: "20m"
dependencies: [1]
---

# Phase 2: Validate

## Overview

Prove the move is behavior-preserving: same collected test count, full suite
green, pyright clean. No code changes here — verification only. If anything
fails, fix in Phase 1 and re-run.

## Requirements

- Functional: collected count matches Phase 1 baseline; all tests pass; pyright
  reports no new errors on the relocated test roots.
- Non-functional: requires local Docker (testcontainers spin up Mongo + Redis).

## Architecture

Verification layers, cheapest first:
1. Static — pytest collection (catches import/path breakage without running).
2. Type — pyright over new `tests/*_test` roots.
3. Dynamic — full `just test` (catches fixture-resolution + relative-import issues).

## Related Code Files

- None modified. Reads: `pyproject.toml`, `pyrightconfig.json`, moved test trees.

## Implementation Steps

1. **Collect-only parity** — count must equal Phase 1 baseline:
   ```bash
   uv run pytest --collect-only -q 2>/dev/null | tail -1
   ```
2. **Pyright** — no new errors:
   ```bash
   pyright
   ```
3. **Full suite** (Docker required):
   ```bash
   just test
   ```
4. **Per-package recipe smoke** — confirm rewired `test-pkg`:
   ```bash
   just test-pkg api
   ```
5. **Reference sweep** — zero stale path hits:
   ```bash
   grep -rn "packages/pocketquant-.*tests" \
     --include=*.toml --include=*.json --include=*.yml \
     --include=justfile --include=*.md . | grep -v node_modules || echo "clean"
   ```

## Success Criteria

- [x] Collected test count == Phase 1 baseline (403 == 403).
- [x] `pyright` clean (0 new errors from relocated roots; 96 vs 97 pre-move, set-diff confirms no new).
- [x] `just test` green (391 passed, 12 skipped, 0 failed).
- [x] `just test-pkg api` runs the api suite from new path (113 passed, 12 skipped).
- [x] Reference sweep returns "clean".

## Risk Assessment

- **Docker unavailable** → integration tests error on container start, not a move
  regression. If Docker absent, run `pytest --collect-only` + pyright (steps 1-2,5)
  and defer dynamic run; note as unresolved.
- **Count mismatch** → indicates a tree or `__init__.py` not moved, or stale cache;
  re-clean caches and inspect `git status` before re-running.
