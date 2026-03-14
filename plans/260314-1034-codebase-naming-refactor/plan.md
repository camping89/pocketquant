---
title: "Codebase Naming Refactor"
description: "Standardize naming across DI folder, application services, and infrastructure clients"
status: completed
priority: P1
effort: 3h
branch: feat/strategy-init
tags: [refactor, naming, consistency]
created: 2026-03-14
completed: 2026-03-14
---

# Codebase Naming Refactor

**Goal:** Make codebase self-documenting by standardizing naming conventions across layers.

**Scope:** 3 rename categories, ~60 file edits, zero behavior change.

**Brainstorm report:** [brainstorm-260314-1028-codebase-naming-simplification.md](../reports/brainstorm-260314-1028-codebase-naming-simplification.md)

## Phases

| # | Phase | Files Changed | Status |
|---|-------|--------------|--------|
| 1 | [Rename DI folder](./phase-01-rename-di-folder.md) | ~10 | completed |
| 2 | [Rename Application Services](./phase-02-rename-application-services.md) | ~35 | completed |
| 3 | [Rename Infrastructure Clients](./phase-03-rename-infrastructure-clients.md) | ~12 | completed |
| 4 | [Verify & Update Docs](./phase-04-verify-and-update-docs.md) | ~6 | completed |

## Execution Order

1. Phase 1 first (DI folder) -- other phases import from it
2. Phase 2 next (app services) -- depends on new DI paths
3. Phase 3 (infra clients) -- independent but logically after
4. Phase 4 last (verify everything compiles, tests pass, update docs)

## Commit Strategy

One commit per phase with `refactor:` prefix. Or single squash commit if preferred:

```
refactor: standardize naming across DI, application, and infrastructure layers
```

## Risk Mitigation

- Each phase: run `ruff check src/` + `pyright src/` + `pytest` after file renames
- Git mv for renames to preserve blame history
- No class behavior changes -- purely mechanical rename

## What Does NOT Change

- 27 CQRS Handler classes
- 7 Repository classes
- BrokerFactory
- Domain layer
- Features vertical slice structure
- DI Provider class names (only folder/filenames change)
