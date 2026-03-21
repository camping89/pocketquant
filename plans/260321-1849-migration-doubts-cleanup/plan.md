---
title: "Migration Doubts Cleanup"
description: "Resolve all 7 migration doubts: remove dead coupling, move repos, fix config, restructure tests"
status: completed
priority: P1
effort: 4h
branch: feat/strategy-init
tags: [refactoring, cleanup, migration, ddd]
created: 2026-03-21
completed: 2026-03-21
blockedBy: []
blocks: []
---

# Migration Doubts Cleanup

Resolve all items from `docs/migration-doubts-and-notes.md`. 5 actionable phases + 3 no-ops.

## Dependency Graph

```
Phase 1 (remove dead coupling)
    ↓
Phase 2 (move order/position repos to trading)
    ↓
Phase 3 (verify DI imports + import-linter)
    ↓
Phase 4 (fix config .env resolution)  ← independent, but ordered for clean commits
    ↓
Phase 5 (restructure tests per-package)
```

## Phases

| Phase | File | Status | Risk | Effort |
|-------|------|--------|------|--------|
| 1 | [phase-01-remove-strategy-coupling.md](phase-01-remove-strategy-coupling.md) | completed | Zero | 30m |
| 2 | [phase-02-move-trading-repos.md](phase-02-move-trading-repos.md) | completed | Low | 45m |
| 3 | [phase-03-verify-di-imports.md](phase-03-verify-di-imports.md) | completed | Low | 30m |
| 4 | [phase-04-fix-config-env-resolution.md](phase-04-fix-config-env-resolution.md) | completed | Low | 20m |
| 5 | [phase-05-restructure-tests.md](phase-05-restructure-tests.md) | completed | Medium | 60m |

## No-Ops (Mark Resolved)

- **Item 2** (Backtest repos): Already in correct location (`backtest/persistence/`)
- **Item 4** (Namespace packages): Already correct (no `__init__.py` at `pocketquant/` level)
- **Item 7** (Strategy location): Stays in `core/concepts/strategy/` (shared kernel)

## Success Criteria

- [x] Zero `ignore_imports` in pyproject.toml import-linter config
- [x] `lint-imports` passes with no violations
- [x] No backtest→trading imports exist
- [x] order/position repos live in trading package
- [x] Config resolves .env without hardcoded parent count
- [x] Tests organized per-package, all pass
- [x] `docs/migration-doubts-and-notes.md` updated — all items resolved

## Context

- Brainstorm: previous conversation (2026-03-21)
- Related plan: `260321-0902-monorepo-package-split` (predecessor, completed in practice)
