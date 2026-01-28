# Brainstorm Report: DDD + Vertical Slice Architecture Refactor

**Date:** 2026-01-27 | **Status:** Agreed | **Scope:** Full architecture refactor

## Problem Statement

Current codebase needs refactoring to serve as reference architecture template for future scalable monolith projects with:
- Vertical Slice Architecture
- Domain-Driven Design (DDD) with tactical patterns
- CQRS with Mediator pattern
- Centralized constants/config
- Cross-cutting concerns (correlation, health, idempotency, rate limiting)
- Integration readiness (webhooks, HTTP client)

## Current Issues

### Scattered Constants
- `OHLCV_COLLECTION` defined in 2 places
- `SYNC_STATUS_COLLECTION` defined in 3 places
- `SYMBOLS_COLLECTION` defined in 2 places
- Cache keys hardcoded across files
- TTLs scattered (60s, 300s, 3600s)

### Missing DDD Layers
- No explicit Domain Layer (pure business logic)
- Services mix business logic with infrastructure
- No Application Layer (commands/queries/handlers)

### Missing Cross-Cutting Concerns
- No request correlation/tracing
- No health check aggregation
- No idempotency support
- No rate limiting infrastructure
- No webhook infrastructure

## Agreed Solution

### Directory Structure

```
src/
├── common/                            # Pure utilities + coordinators
│   ├── constants.py                   # Centralized (prefixed sections)
│   ├── config.py
│   ├── logging/
│   ├── mediator/                      # CQRS Mediator pattern
│   ├── messaging/                     # In-memory event bus
│   ├── tracing/                       # Correlation ID
│   ├── health/                        # Health coordinator
│   ├── idempotency/                   # Middleware
│   └── rate_limit/                    # Middleware
│
├── infrastructure/                    # ALL external I/O
│   ├── persistence/
│   │   ├── mongodb.py                 # Database singleton
│   │   └── redis.py                   # Cache singleton
│   ├── scheduling/                    # APScheduler
│   ├── tradingview/                   # External API
│   ├── http_client/                   # Resilient client
│   └── webhooks/                      # Dispatch
│
├── domain/                            # PURE business logic
│   ├── ohlcv/
│   │   ├── aggregate.py
│   │   ├── entities.py
│   │   ├── value_objects.py
│   │   ├── events.py
│   │   └── services/
│   ├── symbol/
│   ├── quote/
│   └── shared/
│
├── features/                          # Application Layer
│   └── market_data/
│       ├── sync/                      # By operation
│       │   ├── command.py
│       │   ├── handler.py
│       │   ├── event_handlers.py
│       │   ├── jobs.py
│       │   └── dto.py
│       ├── ohlcv/
│       ├── quote/
│       ├── status/
│       └── api/
│
└── main.py
```

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Constants | Single `constants.py` with prefixes | Easy discovery, avoid duplication |
| DDD Style | Full tactical DDD + CQRS | Reference template for future projects |
| Dispatch | Mediator pattern | Central routing, testable |
| Events | In-memory event bus | Simple for monolith, swappable later |
| Repository | None (direct DB access) | Less abstraction, simpler |
| Domain location | `src/domain/` (separate) | Clear separation from features |
| Aggregate structure | Root folder with children | Co-located entities, events, services |
| Feature slices | By operation (not cmd/query) | Natural grouping per endpoint |
| I/O code | `src/infrastructure/` | All external calls in one place |
| MongoDB driver | PyMongo Async API | Official replacement for Motor |

### Constants Structure

```python
# src/common/constants.py
# COLLECTIONS - MongoDB collection names
COLLECTION_OHLCV = "ohlcv"
COLLECTION_SYNC_STATUS = "sync_status"
COLLECTION_SYMBOLS = "symbols"

# CACHE_KEYS - Redis key patterns
CACHE_KEY_QUOTE_LATEST = "quote:latest:{exchange}:{symbol}"
CACHE_KEY_BAR_CURRENT = "bar:current:{exchange}:{symbol}:{interval}"
CACHE_KEY_OHLCV = "ohlcv:{symbol}:{exchange}:{interval}:{limit}"

# TTL - Cache time-to-live
TTL_QUOTE_LATEST = 60
TTL_BAR_CURRENT = 300
TTL_OHLCV_QUERY = 300
TTL_DEFAULT = 3600

# LIMITS
LIMIT_TVDATAFEED_MAX_BARS = 5000
LIMIT_BULK_SYNC_MAX = 50

# HEADERS
HEADER_CORRELATION_ID = "X-Correlation-ID"
```

### DDD Layer Responsibilities

| Layer | Contains | Can Import |
|-------|----------|------------|
| Domain | Aggregates, Entities, VOs, Events, Domain Services | Nothing external |
| Application | Commands, Queries, Handlers, Event Handlers, Jobs, DTOs | Domain, Infrastructure |
| Infrastructure | MongoDB, Redis, TradingView, HTTP Client | External systems |
| Common | Mediator, EventBus, Middleware, Logging | Python stdlib |

### Removed from Scope
- ❌ Repository pattern (direct DB access)
- ❌ Feature flags (not needed for monolith)
- ❌ Outbox pattern (only for microservices)

### Added for Integration Readiness
- ✅ Webhook dispatcher
- ✅ Idempotency middleware
- ✅ Rate limit middleware
- ✅ Resilient HTTP client
- ✅ Correlation ID propagation

## Implementation Phases (Suggested)

1. **Phase 1:** Create `constants.py`, move scattered constants
2. **Phase 2:** Create `infrastructure/` layer, move DB/Cache/Scheduler
3. **Phase 3:** Create `domain/` layer with aggregates
4. **Phase 4:** Create `common/mediator/` and event bus
5. **Phase 5:** Refactor features to use CQRS pattern
6. **Phase 6:** Add cross-cutting middleware
7. **Phase 7:** Add integration infrastructure (webhooks, HTTP client)
8. **Phase 8:** Update tests and documentation

## Success Criteria

- [ ] No duplicate constant definitions
- [ ] Domain layer has zero I/O imports
- [ ] All commands/queries go through Mediator
- [ ] Correlation ID in all log entries
- [ ] Health endpoint shows all dependencies
- [ ] Idempotency works for POST endpoints
- [ ] All tests pass
- [ ] Documentation updated

## Risks

| Risk | Mitigation |
|------|------------|
| Large refactor, many file moves | Incremental phases, tests after each |
| Breaking existing functionality | Comprehensive test coverage first |
| Import cycle issues | Clear layer boundaries, dependency rules |

## Sources

- [PyMongo Async Migration Guide](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/)
- [Motor Deprecation Notice](https://motor.readthedocs.io/en/stable/differences.html)

---

*Report generated from brainstorm session 260127-2029*
