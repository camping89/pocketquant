---
title: "Unify Codebase with Pydantic Everywhere"
description: "Replace dataclass with Pydantic across all layers - commands, domain entities, MongoDB models"
status: completed
priority: P2
effort: 3h
branch: feat/strategy-init
tags: [refactoring, cqrs, pydantic, fastapi, ddd]
created: 2026-02-01
updated: 2026-02-01
---

# Unify Codebase with Pydantic Everywhere

## Philosophy

**Simplified approach (like .NET Entity Framework):**
- One class serves as both domain entity AND persistence model
- Pydantic models with business methods = aggregate roots
- No separation between "domain dataclass" and "persistence Pydantic"
- Follows YAGNI - don't create abstractions you don't need

## Context

- Decision: [decision-merge-pydantic-request-command-for-cqrs.md](../reports/decision-merge-pydantic-request-command-for-cqrs.md)
- Inspiration: .NET approach where EF entities ARE the aggregate roots

## Current State (dataclass scattered)

| Layer | Current | Target |
|-------|---------|--------|
| API Commands | dataclass | Pydantic |
| API Queries | dataclass | Pydantic |
| DTOs | dataclass | Pydantic |
| Domain Aggregates | dataclass | Pydantic |
| Domain Value Objects | dataclass | Pydantic (frozen) |
| Domain Events | dataclass | Pydantic (frozen) |
| MongoDB Models | Pydantic | Pydantic (keep) |

## Target State (Pydantic everywhere)

```python
# ONE class = Domain Entity + MongoDB Document + API Response
class Order(BaseModel):
    id: str
    symbol: str
    status: OrderStatus = OrderStatus.PENDING

    model_config = ConfigDict(frozen=False)  # Mutable entity

    def submit(self) -> None:
        """Business logic lives here."""
        if self.status != OrderStatus.PENDING:
            raise ValueError("Can only submit pending orders")
        self.status = OrderStatus.SUBMITTED

    def to_mongo(self) -> dict:
        return self.model_dump()
```

## Phases

| Phase | Description | Status | Effort |
|-------|-------------|--------|--------|
| [Phase 1](phase-01-implementation-convert-market-data-sync-commands-to-pydantic.md) | market_data/sync commands + routes + DTOs | completed | 45m |
| [Phase 2](phase-02-implementation-convert-market-data-quote-commands-to-pydantic.md) | market_data/quote commands | completed | 20m |
| [Phase 3](phase-03-implementation-convert-backtesting-commands-to-pydantic.md) | backtesting commands + routes | completed | 30m |
| [Phase 4](phase-04-implementation-convert-strategy-commands-to-pydantic.md) | strategy commands + routes | completed | 15m |
| [Phase 5](phase-05-implementation-convert-domain-layer-to-pydantic.md) | Domain aggregates, value objects, events | completed | 45m |
| [Phase 6](phase-06-validation-tests-type-checking-openapi.md) | Tests, type checking, cleanup | completed | 15m |

## Success Criteria

- [x] All commands/queries are Pydantic BaseModel
- [x] All domain entities are Pydantic BaseModel
- [x] All value objects are Pydantic with frozen=True
- [x] All domain events are Pydantic with frozen=True
- [x] No separate Request classes in routes (where applicable)
- [x] Handlers return Pydantic models directly
- [x] Domain purity test still valid (checks I/O imports, not Pydantic)
- [x] All tests pass (56 passed)
- [x] Type checking passes (pyright: 0 errors)

## Key Pattern

```python
# Value Object (immutable)
class Interval(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: str

    @field_validator("value")
    def validate_interval(cls, v):
        if v not in VALID_INTERVALS:
            raise ValueError(f"Invalid: {v}")
        return v

# Aggregate Root (mutable, with business logic)
class Order(BaseModel):
    id: str
    status: OrderStatus = OrderStatus.PENDING
    _events: list = PrivateAttr(default_factory=list)

    def submit(self) -> None:
        self.status = OrderStatus.SUBMITTED
        self._events.append(OrderSubmittedEvent(...))

    def to_mongo(self) -> dict:
        return self.model_dump()

# Domain Event (immutable)
class OrderSubmittedEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    submitted_at: datetime
```

## Files to Update Summary

| Directory | Files | Change |
|-----------|-------|--------|
| src/features/*/handlers/ | commands.py | dataclass → Pydantic |
| src/features/*/sync/ | dto.py, command.py | dataclass → Pydantic |
| src/domain/*/ | aggregates, value_objects, events | dataclass → Pydantic |
| tests/unit/domain/ | test_domain_purity.py | Remove or update |
