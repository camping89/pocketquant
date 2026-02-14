---
title: "Clean Architecture Refactor"
description: "Move support code out of features/ into domain, application, infrastructure layers"
status: completed
priority: P1
effort: 16h
branch: feat/strategy-init
tags: [refactor, architecture, clean-architecture]
created: 2026-02-14
completed: 2026-02-14
---

# Clean Architecture Refactor

## Overview

Move managers, engines, repositories, services, and models out of `features/*/base/` into proper Clean Architecture layers. Features become thin operation layers (commands, queries, handlers, routes, DTOs only).

## Context

- Brainstorm: [brainstorm report](../reports/brainstorm-260214-1326-clean-architecture-refactor.md)
- Scout: Import dependency analysis completed — 15 pure files, 3 mixed, 6 infrastructure, 9 application services

## Target Layer Rules

```
features/ ──→ application/ ──→ domain/
    │              │
    └──────────────┴──→ infrastructure/ ──→ domain/
```

- **domain/** — ZERO I/O imports. Pure logic only.
- **application/** — Per-feature orchestrators. Can use domain + infrastructure.
- **infrastructure/** — Persistence, providers, file I/O. Implements domain interfaces.
- **features/** — ONLY commands, queries, handlers, routes, DTOs, routers.

## Phases

| # | Phase | Status | Effort | Link |
|---|-------|--------|--------|------|
| 1 | Scaffold layers & shared contracts | Completed | 1h | [phase-01](./phase-01-scaffold-layers.md) |
| 2 | Migrate trading (proof-of-concept) | Completed | 3h | [phase-02](./phase-02-migrate-trading.md) |
| 3 | Migrate strategy | Completed | 3h | [phase-03](./phase-03-migrate-strategy.md) |
| 4 | Migrate backtesting | Completed | 4h | [phase-04](./phase-04-migrate-backtesting.md) |
| 5 | Migrate market_data | Completed | 4h | [phase-05](./phase-05-migrate-market-data.md) |
| 6 | Cleanup, verify, update docs | Completed | 1h | [phase-06](./phase-06-cleanup-verify.md) |

## Dependencies

- Each phase depends on Phase 1 (scaffold)
- Phases 2-5 are sequential (each validates the pattern before the next)
- Phase 6 depends on all others

## Completion Summary

All 6 phases completed successfully on 2026-02-14.

**Key Metrics:**
- 60/60 tests passing
- 0 Pyright errors
- 0 dependency direction violations (3 documented pragmatic exceptions)
- 1 orphan directory cleaned up
- Domain purity test strengthened with additional forbidden imports
- 41 ruff issues auto-fixed

**Achievements:**
- All support code moved out of features/ to proper Clean Architecture layers
- Features now contain ONLY: commands, queries, handlers, routes, DTOs
- Domain layer enforced with zero I/O imports (except documented exceptions)
- Application layer created with per-feature orchestrators
- Infrastructure layer consolidates persistence and provider implementations
- Full test coverage validates architecture compliance
