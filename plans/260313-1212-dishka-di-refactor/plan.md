---
title: "Migrate DI from plain constructors to dishka"
description: "Replace Services frozen dataclass + manual handler registration with dishka container for auto-wiring"
status: pending
priority: P2
effort: 6h
branch: feat/strategy-init
tags: [di, dishka, refactor, infrastructure]
created: 2026-03-13
---

# Dishka DI Migration Plan

## Goal

Replace the hand-rolled DI pattern (frozen `Services` dataclass + 28-handler manual registration + `Depends(get_mediator)` boilerplate) with **dishka** — an async-first DI framework that auto-resolves constructor deps via type hints.

## Current State

| File | LOC | Role | Fate |
|------|-----|------|------|
| `src/services.py` | 73 | Frozen dataclass holding 22 singletons | DELETE |
| `src/handler_registration.py` | 118 | Manual construction of 28 CQRS handlers | DELETE |
| `src/dependencies.py` | 31 | 3 `Depends()` functions for route injection | DELETE |
| `src/main.py` lifespan | 174 | 21-step imperative init + try/finally shutdown | SIMPLIFY |
| `src/main_extensions.py` | 143 | `ensure_all_indexes`, health checks, jobs | MODIFY |
| 27 route files | ~30 each | `Annotated[Mediator, Depends(get_mediator)]` | MODIFY |
| 2 middleware files | ~60 each | `request.app.state.cache` | KEEP (no change) |

## Architecture Decision

- **APP scope**: All 22 existing services + 28 handlers (singletons for app lifetime)
- **REQUEST scope**: Not needed now; all current routes just dispatch to Mediator. Reserve for future per-request context
- **Middleware**: Keep `app.state.cache`/`app.state.database` for hot-path middleware (IdempotencyMiddleware, RateLimitMiddleware). These run outside dishka's REQUEST scope
- **BacktestRunner / GridOptimizer**: Stay manual (created fresh per handler invocation, not in container)
- **Route injection**: `DishkaRoute` on parent routers + `FromDishka[Mediator]` in routes. One route uses `FromDishka[QuoteService]`

## Phases

| # | Phase | Status | Effort |
|---|-------|--------|--------|
| 1 | [Install dishka + create providers](./phase-01-create-providers.md) | pending | 2h |
| 2 | [Migrate lifespan to dishka container](./phase-02-migrate-lifespan.md) | pending | 1.5h |
| 3 | [Update routes to FromDishka](./phase-03-update-routes.md) | pending | 1h |
| 4 | [Delete dead code](./phase-04-delete-dead-code.md) | pending | 0.5h |
| 5 | [Update tests](./phase-05-update-tests.md) | pending | 1h |

## Key Dependencies

- dishka >= 1.4 (requires Python 3.10+; project uses 3.14)
- dishka[fastapi] extra for `setup_dishka`, `DishkaRoute`, `FromDishka`

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Async post-init (Database.connect, etc.) | Medium | Use async generator factories with yield pattern |
| Middleware still needs app.state.cache | Low | Keep setting app.state in lifespan; dishka handles lifecycle |
| Handler registration order (Mediator) | Medium | Dedicated provider factory that resolves all handlers and registers them |
| SyncSymbolHandler shared instance | Low | Dishka auto-caches within scope; BulkSyncHandler depends on SyncSymbolHandler type |
| Event handler registration (@event_handler) | Medium | Post-init calls in generator factories |
