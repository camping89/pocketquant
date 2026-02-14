---
title: "Consolidate persistence into top-level src/persistence/ package"
description: "Move all DB/cache code to src/persistence/, create missing repos, eliminate raw get_collection() calls"
status: pending
priority: P1
effort: 3h
branch: feat/strategy-init
tags: [refactor, persistence, clean-architecture]
created: 2026-02-14
---

# Persistence Layer Consolidation

## Goal
Replace scattered `Database.get_collection()` calls across 13 files with proper repository classes, consolidate all persistence code under `src/persistence/`.

## Current State
- 30 `Database.get_collection()` calls across handlers, application services, and repos
- Persistence code lives in `src/infrastructure/persistence/` (repos, schemas, mongodb, redis)
- Constants (collection names, cache keys, TTLs) in `src/common/constants.py`
- Re-export shims: `src/common/database/`, `src/common/cache/`
- 60/60 tests pass, none import directly from infrastructure.persistence

## Phases

| Phase | Description | Status |
|-------|-------------|--------|
| [Phase 1](./phase-01-scaffold-and-move.md) | Create `src/persistence/`, move files, update re-export shims | pending |
| [Phase 2](./phase-02-new-repositories.md) | Create 4 new repos + base class, wire into handlers | pending |
| [Phase 3](./phase-03-cleanup-and-verify.md) | Delete old path, update main.py imports, final test run | pending |

## Key Decisions
- **No base class ABC** -- just a minimal mixin with `_collection()` helper (KISS)
- **Keep static method pattern** -- matches existing OrderRepository/PositionRepository
- **Keep constants in `src/common/constants.py`** -- non-persistence constants (HEADER_*, LIMIT_*, INTERVAL_*) still need it; moving only collection names creates import confusion. Leave as-is.
- **Re-export shims stay** -- `src/common/database/` and `src/common/cache/` just point to new location

## Risk
- Import chain breakage: mitigated by updating re-export shims first (phase 1)
- Merge conflicts if other branches touch handlers: low risk, branch is feature-scoped

## Success Criteria
- Zero `Database.get_collection()` calls outside `src/persistence/`
- All 60 tests pass after each phase
- `src/infrastructure/persistence/` deleted
- All imports resolve to `src/persistence/` paths
