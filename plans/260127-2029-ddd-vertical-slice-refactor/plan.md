---
title: "DDD + Vertical Slice Architecture Refactor"
description: "Reference architecture template with CQRS, domain layer, cross-cutting concerns"
status: completed
priority: P1
effort: 16h
branch: master
tags: [architecture, ddd, cqrs, refactor]
created: 2026-01-27
---

# DDD + Vertical Slice Architecture Refactor

## Overview

Refactor PocketQuant (~3,600 LOC) into a reference architecture template combining:
- Domain-Driven Design (tactical patterns)
- CQRS with Mediator pattern
- Vertical Slice Architecture
- Cross-cutting concerns (correlation, health, idempotency, rate limiting)

**Goal:** Create scalable monolith template for future projects.

## Target Architecture

```
src/
├── common/                     # Pure utilities + coordinators
│   ├── constants.py            # Centralized with prefixes
│   ├── config.py
│   ├── logging/
│   ├── mediator/               # CQRS Mediator
│   ├── messaging/              # In-memory event bus
│   ├── tracing/                # Correlation ID
│   ├── health/                 # Health coordinator
│   ├── idempotency/            # Middleware
│   └── rate_limit/             # Middleware
│
├── infrastructure/             # ALL external I/O
│   ├── persistence/mongodb.py, redis.py
│   ├── scheduling/scheduler.py
│   ├── tradingview/provider.py, websocket.py, base.py
│   ├── http_client/client.py
│   └── webhooks/dispatcher.py
│
├── domain/                     # PURE business logic (zero I/O)
│   ├── ohlcv/aggregate.py, entities.py, value_objects.py, events.py, services/
│   ├── symbol/aggregate.py, value_objects.py
│   ├── quote/aggregate.py, events.py
│   └── shared/value_objects.py, events.py
│
├── features/market_data/       # Application Layer
│   ├── sync/command.py, handler.py, event_handlers.py, jobs.py, dto.py
│   ├── ohlcv/query.py, handler.py, dto.py
│   ├── quote/subscribe_command.py, subscribe_handler.py, ...
│   ├── status/query.py, handler.py, dto.py
│   └── api/routes.py, quote_routes.py
│
└── main.py
```

## Key Constraints

| Constraint | Details |
|------------|---------|
| No repository pattern | Direct DB access in handlers |
| Domain layer purity | ZERO I/O imports in `domain/` |
| API contracts unchanged | Existing endpoints must work |
| Test pass after each phase | Incremental validation |

## Phases

| Phase | Title | Effort | Status |
|-------|-------|--------|--------|
| [1](phase-01-centralize-constants.md) | Centralize Constants | 1h | completed |
| [2](phase-02-infrastructure-layer.md) | Infrastructure Layer | 2h | completed |
| [3](phase-03-domain-layer.md) | Domain Layer | 3h | completed |
| [4](phase-04-mediator-eventbus.md) | Mediator + Event Bus | 2h | completed |
| [5](phase-05-refactor-features-cqrs.md) | Refactor Features to CQRS | 3h | completed |
| [6](phase-06-cross-cutting-middleware.md) | Cross-Cutting Middleware | 2h | completed |
| [7](phase-07-integration-infrastructure.md) | Integration Infrastructure | 2h | completed |
| [8](phase-08-tests-documentation.md) | Tests + Documentation | 1h | completed |

## Success Criteria

- [ ] No duplicate constant definitions
- [ ] Domain layer has zero I/O imports
- [ ] All commands/queries through Mediator
- [ ] Correlation ID in all log entries
- [ ] Health endpoint shows all dependencies
- [ ] Idempotency works for POST endpoints
- [ ] All tests pass
- [ ] Documentation updated

## Dependencies

- Phase 1-2: Independent, can run in parallel
- Phase 3: Requires Phase 2 (infrastructure)
- Phase 4: Requires Phase 1 (constants)
- Phase 5: Requires Phase 3, 4 (domain + mediator)
- Phase 6: Requires Phase 5 (features refactored)
- Phase 7: Requires Phase 5
- Phase 8: Requires Phase 6, 7

## Risks

| Risk | Mitigation |
|------|------------|
| Large refactor scope | Incremental phases, test after each |
| Import cycles | Clear layer boundaries, dependency rules |
| Breaking existing API | Keep route signatures unchanged |

## Research References

- [DDD CQRS Patterns](research/researcher-ddd-cqrs-patterns.md)
- [Middleware Patterns](research/researcher-middleware-patterns.md)
- [Architecture Brainstorm](../reports/brainstorm-260127-2029-ddd-vertical-slice-refactor.md)

---

## Validation Summary

**Validated:** 2026-01-27
**Questions asked:** 5

### Confirmed Decisions

| Decision | User Choice |
|----------|-------------|
| Service deletion after CQRS | Delete immediately (no fallback) |
| Rate limiting config | 200 req/10s (less restrictive) |
| Event bus durability | In-memory (accept loss on crash) |
| Outbox pattern | Not needed for monolith |
| Phase parallelization | Keep sequential execution |

### Action Items

- [ ] Update Phase 6 rate limit config: `capacity=200, refill_rate=20`

### Notes

- User initially considered persistent outbox but reconsidered given monolith simplicity
- Sequential execution preferred for easier tracking despite Phase 1+2 independence
