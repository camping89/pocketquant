---
title: "Backend CQRS Refactor"
description: "Remove repository layer, add IDataProvider interface, rename QuoteAggregator to BarManager"
status: completed
priority: P2
effort: 4h
branch: master
tags: [refactor, cqrs, architecture]
created: 2026-01-26
---

# Backend CQRS Refactor Plan

## Overview

Migrate from Repository Pattern to direct DB access in services (CQRS style), add infrastructure interfaces for external providers, and rename managers per naming conventions.

## Dependency Graph (Parallel Strategy)

```
Phase 1A ─────────┐
(IDataProvider)   │
                  ├──> Phase 2 ──> Phase 3 ──> Phase 4 ──> Phase 5
Phase 1B ─────────┤    (Inline     (Inline    (Update     (Cleanup)
(Error Fixes)     │     OHLCV      Symbol     Imports)
                  │     Repo)      Repo)
Phase 1C ─────────┘
(BarManager)
```

**Parallel Execution:**
- Phase 1A, 1B, 1C run in PARALLEL (no file overlap)
- Phase 2-5 run SEQUENTIALLY (depend on Phase 1)

## File Ownership Matrix

| Phase | Files (EXCLUSIVE) | Action |
|-------|------------------|--------|
| 1A | `providers/base.py`, `providers/tradingview.py` | Create/Modify |
| 1B | `scheduler.py`, `tradingview_ws.py` | Modify |
| 1C | `managers/`, `services/quote_aggregator.py` | Create/Move |
| 2 | `services/data_sync_service.py`, `jobs/sync_jobs.py` | Modify |
| 3 | `api/routes.py` | Modify |
| 4 | `services/quote_service.py`, `api/quote_routes.py` | Modify |
| 5 | `repositories/` folder | DELETE |

## Phase Summary

| Phase | Description | LOC | Status |
|-------|-------------|-----|--------|
| 1A | Create IDataProvider ABC + implement | ~40 | [x] Complete |
| 1B | Fix bare except in scheduler/ws | ~15 | [x] Complete |
| 1C | Rename QuoteAggregator → BarManager | ~20 | [x] Complete |
| 2 | Inline OHLCVRepository into services | ~150 | [x] Complete |
| 3 | Inline SymbolRepository into routes | ~60 | [x] Complete |
| 4 | Update imports for BarManager | ~15 | [x] Complete |
| 5 | Delete repository folder, verify | ~10 | [x] Complete |

## Success Criteria

- [x] No `repositories/` folder exists
- [x] `providers/base.py` exists with IDataProvider ABC
- [x] TradingViewProvider implements IDataProvider
- [x] `managers/bar_manager.py` exists (from quote_aggregator)
- [x] No bare `except:` without logging
- [x] All imports verified working
- [x] FastAPI app loads with 21 routes
- [x] Each file < 200 LOC

## Linked Files

- [Phase 1A: Infrastructure Interfaces](./phase-01a-infrastructure-interfaces.md)
- [Phase 1B: Error Handling Fixes](./phase-01b-error-handling-fixes.md)
- [Phase 1C: BarManager Rename](./phase-01c-bar-manager-rename.md)
- [Phase 2: Inline OHLCV Repository](./phase-02-inline-ohlcv-repository.md)
- [Phase 3: Inline Symbol Repository](./phase-03-inline-symbol-repository.md)
- [Phase 4: Update BarManager Imports](./phase-04-update-barmanager-imports.md)
- [Phase 5: Cleanup and Verify](./phase-05-cleanup-and-verify.md)

## Research References

- [CQRS Patterns Research](./research/researcher-01-cqrs-patterns.md)
- [ABC Interfaces Research](./research/researcher-02-abc-interfaces.md)
- [Brainstorm Report](../reports/brainstorm-260126-1050-backend-architecture-refactor.md)
