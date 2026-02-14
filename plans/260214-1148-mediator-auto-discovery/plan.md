# Auto-Discover & Register CQRS Handlers to Mediator

**Created:** 2026-02-14 | **Status:** Draft | **Branch:** feat/strategy-init

## Problem

`main.py` has ~90 lines of manual imports + `mediator.register()` calls for 28 handlers.
Adding a new handler requires touching main.py every time — error-prone, violates OCP.
No guard against accidentally registering two handlers for the same command/query.

## Solution

Mirror the existing `@event_handler` + `EventRegistry` pattern but for CQRS handlers:
1. `@handles(RequestType)` class decorator on handler classes
2. `HandlerRegistry` scans features, discovers handlers, validates uniqueness
3. `DuplicateHandlerError` thrown if >1 handler claims same command/query
4. Per-feature `register_handlers()` functions handle DI + instantiation
5. `main.py` reduced to ~10 lines of feature-level registration

## Phases

| # | Phase | Status | File |
|---|-------|--------|------|
| 1 | Core: decorator + registry + exception | Pending | [phase-01](./phase-01-core-registry.md) |
| 2 | Decorate all 28 handlers with `@handles` | Pending | [phase-02](./phase-02-decorate-handlers.md) |
| 3 | Per-feature `register_handlers()` functions | Pending | [phase-03](./phase-03-feature-registrations.md) |
| 4 | Simplify main.py lifespan | Pending | [phase-04](./phase-04-simplify-main.md) |

## Key Constraints

- **One handler per command/query** — `DuplicateHandlerError` if violated
- **Existing DI pattern preserved** — handlers still get deps via constructor
- **No DI container** — KISS; feature-level factory functions handle wiring
- **Backward compatible** — `mediator.register()` still works, just adds duplicate check
