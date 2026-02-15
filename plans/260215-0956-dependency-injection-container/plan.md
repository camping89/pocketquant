---
title: "Dependency Injection Container with dependency-injector"
description: "Introduce proper IoC via dependency-injector library, replacing manual wiring in main.py"
status: completed
priority: P1
effort: 10h
branch: feat/strategy-init
tags: [refactor, backend, infra]
created: 2026-02-15
---

# Dependency Injection Container

Replace manual wiring in `src/main.py` + `src/main_extensions.py` with a single `AppContainer` using [dependency-injector](https://python-dependency-injector.ets-labs.org/).

## Motivation

- Current wiring is imperative spaghetti in `main_extensions.py` (~125 LOC of manual construction)
- Static class-method singletons (Database, Cache, JobScheduler) are untestable and hide dependencies
- Repositories use global class-level state via `BaseRepository._collection()` -- impossible to inject alternatives
- Handler registration manually passes dependencies through `register.py` files
- `app.state` used as service locator -- invisible, untyped dependency

## Design Decisions

1. **One flat `AppContainer`** -- ~40 providers, no sub-containers
2. **No scoped scope** -- Motor manages connection pool, no ORM session
3. **Database/Cache: class-level -> instance-level** -- Resource providers with async init/shutdown
4. **Repositories: static -> instance-based** -- inject Database via constructor
5. **Handlers: Factory providers (transient)** -- fresh instance per resolution, not shared singletons
6. **Routes: `Depends()` from container** -- replace `app.state` service locator

## Phases

| # | Phase | Status | Effort | File |
|---|-------|--------|--------|------|
| 1 | Install + container skeleton | completed | 1h | [phase-01](./phase-01-container-skeleton.md) |
| 2 | Persistence layer instance-based DI | completed | 3h | [phase-02](./phase-02-persistence-layer-di.md) |
| 3 | Infrastructure + domain services | completed | 2h | [phase-03](./phase-03-infrastructure-services.md) |
| 4 | CQRS handlers + mediator wiring | completed | 2h | [phase-04](./phase-04-cqrs-handler-wiring.md) |
| 5 | FastAPI integration + cleanup | completed | 2h | [phase-05](./phase-05-fastapi-integration-cleanup.md) |

## Dependencies

- Phase 2 depends on Phase 1 (container must exist)
- Phase 3 depends on Phase 2 (services depend on persistence)
- Phase 4 depends on Phase 3 (handlers depend on services)
- Phase 5 depends on Phase 4 (routes depend on everything)

## Risk Summary

- **Breaking existing tests**: repositories switch from classmethod to instance -- all test mocks must update
- **Circular imports**: container imports all modules; careful ordering required
- **Async Resource lifecycle**: must wire init/shutdown into FastAPI lifespan correctly
- **dependency-injector + Python 3.14**: verify compatibility before starting

## Red Team Review

### Session — 2026-02-15
**Findings:** 14 (10 accepted, 4 rejected)
**Severity breakdown:** 3 Critical, 5 High, 6 Medium

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Test fixture collapse — no migration strategy | Critical | Accept | Phase 2 |
| 2 | Python 3.14 compat is plan blocker, not Phase 1 task | Critical | Accept | Phase 1 |
| 3 | Container init failure leaks connections | Critical | Accept | Phase 5 |
| 4 | Resource init order unverified | High | Accept | Phase 3 |
| 5 | Backward compat `_default_instance` zombie path | High | Accept | Phase 2 |
| 6 | Circular import time bomb (container ↔ handler) | High | Accept | Phase 4 |
| 7 | Shutdown race — DB disconnects while jobs in-flight | High | Accept | Phase 5 |
| 8 | sync_jobs.py caller broken between phases | High | Accept | Phase 3 |
| 9 | Container exceeds 200 LOC | Medium | Reject | — |
| 10 | Health check closures capture stale instances | Medium | Reject | — |
| 11 | Container on app.state exposes services | Medium | Reject | — |
| 12 | Missing BarManager/QuoteService registration | Medium | Accept | Phase 3 |
| 13 | Credential exposure via serialization | Medium | Reject | — |
| 14 | Handler count mismatch — audit needed | Medium | Accept | Phase 4 |

## Validation Log

### Session 1 — 2026-02-15
**Trigger:** Initial plan validation after red-team review
**Questions asked:** 4

#### Questions & Answers

1. **[Architecture]** Should CQRS handlers be Singleton (shared instance, reused) or Factory (transient, new per resolution)?
   - Options: Singleton (shared instance) | Factory (transient, new per resolution)
   - **Answer:** Factory (transient)
   - **Rationale:** Handlers should be fresh per resolution for isolation. Even though most are stateless today, Factory prevents accidental state leakage if handlers evolve. Aligns with Design Decision 5 intent but contradicts Phase 4 which originally said Singleton.

2. **[Architecture]** Phase 4 keeps per-feature `register.py` files that pull from container, but this creates a circular import risk (container imports handlers, register.py imports container). How to resolve?
   - Options: Keep register.py files (accept import risk) | Move registration to container module (remove register.py files) | Lazy import in register.py
   - **Answer:** Move registration to container module
   - **Rationale:** Eliminates register.py files entirely. Container module owns both handler provider definitions AND the `register_all_handlers()` function that wires them into Mediator. Single source of truth, no circular imports. Per-feature register.py files become dead code.

3. **[Scope]** EventBus has `@event_handler` decorated subscribers (e.g. domain event listeners). Should these be manually registered or auto-discovered from container?
   - Options: Manual registration (explicit) | Auto-discover in container
   - **Answer:** Auto-discover in container
   - **Rationale:** Container already imports all handler classes. Auto-discovery scans handler instances for `@event_handler` decorated methods and registers them with EventBus automatically. Reduces boilerplate and prevents missed registrations.

4. **[Risk]** What Python version are you running? Plan includes a pre-phase spike for Python 3.14 compatibility verification.
   - Options: Python 3.14 | Python 3.13 or earlier
   - **Answer:** Python 3.14
   - **Rationale:** Confirms the pre-phase spike in Phase 1 is needed. Must verify `dependency-injector` works with Python 3.14 before any implementation begins.

#### Confirmed Decisions
- Handlers: Factory (transient) providers — isolation over performance
- Registration: Container module owns all handler registration — no per-feature register.py files
- Event handlers: Auto-discovered from container — reduces boilerplate
- Python 3.14: Confirmed — pre-phase compat spike is blocking

#### Action Items
- [ ] Update Phase 4: Change handler providers from Singleton to Factory
- [ ] Update Phase 4: Remove register.py simplification steps, replace with container-owned registration
- [ ] Update Phase 4: Add @event_handler auto-discovery step
- [ ] Update Phase 4: Update Related Code Files table (register.py files → delete, not modify)

#### Impact on Phases
- Phase 3: Add @event_handler auto-discovery implementation to container module
- Phase 4: Major rewrite — handlers become Factory providers, register.py files deleted, registration moves to container module
- Phase 5: Simplify — no register.py files to call, just `container.register_all_handlers()`
