---
title: "Persistence Schema Consolidation"
description: "Migrate domain entities/aggregates from dataclass to Pydantic BaseModel, kill persistence schemas, standardize UUID7 _id, add timestamps"
status: completed
priority: P1
effort: 6h
branch: feat/strategy-init
tags: [refactor, persistence, domain, pydantic, consolidation]
created: 2026-03-15
supersedes: [260309-0918-domain-pydantic-to-dataclass-refactor]
---

# Persistence Schema Consolidation

## Motivation

Persistence layer has 3 problems:
1. **Dual hierarchy**: domain dataclasses + Pydantic schemas duplicate every entity
2. **Inconsistent `_id`**: OHLCV uses UUID7 string, Symbol uses MongoDB ObjectId, Order/Position use string
3. **Inconsistent timestamps**: some on entity, some repo-side, some missing

**Decision**: domain entities become Pydantic BaseModel with `to_mongo()`/`from_mongo()`. Kill all persistence schemas. Single source of truth.

**Reverses**: plan `260309-0918-domain-pydantic-to-dataclass-refactor` (completed). That plan moved domain Pydantic → dataclass for DDD purity. This plan reverses that to eliminate schema duplication — pragmatism over purity.

## Brainstorm Report

[brainstorm-260315-0037-persistence-schema-consolidation.md](../reports/brainstorm-260315-0037-persistence-schema-consolidation.md)

## Key Design Decisions

| Decision | Choice |
|----------|--------|
| `_id` strategy | UUID7 string everywhere (`str(uuid7())`) |
| `created_at` | On domain entity, `Field(default_factory=_utc_now)`. Set once. |
| `updated_at` | **Not** on domain entity (except where business-meaningful). Repo `$set`s server-side. |
| `_events` | `PrivateAttr(default_factory=list)` — excluded from `model_dump()` |
| Enums in MongoDB | Stored as `.value` string via `to_mongo()` |
| Value objects/events | Stay dataclass (not persisted, frozen, simple) |
| Quote schemas | Relocate to app/feature layer (Redis cache DTOs, not MongoDB documents) |

### `updated_at` Nuance

- **OrderAggregate**: keeps `updated_at` — it's business logic (tracks state change time in `submit()`, `fill()`, `cancel()`)
- **PositionAggregate**: no `updated_at` — uses `opened_at`/`closed_at` (business timestamps)
- **Bar, SymbolAggregate**: no `updated_at` — repo `$set`s infrastructure timestamp
- **Repos**: always `$set updated_at: datetime.now(UTC)` on every write regardless

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [OHLCV Domain + Repo](./phase-01-ohlcv-domain.md) | completed |
| 2 | [Symbol Domain + Repo](./phase-02-symbol-domain.md) | completed |
| 3 | [Order Domain + Repo](./phase-03-order-domain.md) | completed |
| 4 | [Position Domain + Repo](./phase-04-position-domain.md) | completed |
| 5 | [Quote Schema Relocation](./phase-05-quote-relocation.md) | completed |
| 6 | [Non-Persisted Aggregates + Cleanup](./phase-06-cleanup.md) | completed |

## Scope Summary

### DELETE (persistence schemas)
- `src/persistence/schemas/ohlcv_schema.py` — `OHLCVBase`, `OHLCV`, `SyncStatus` (schema version)
- `src/persistence/schemas/symbol_schema.py` — `SymbolBase`, `Symbol`
- `src/persistence/schemas/order_schema.py` — `OrderDocument`
- `src/persistence/schemas/position_schema.py` — `PositionDocument`

### RELOCATE
- `OHLCVResponse` → `src/features/market_data/ohlcv/get_ohlcv/route.py` (inline or adjacent)
- `Quote`, `QuoteTick`, `AggregatedBar`, `QuoteSubscription` → `src/application/market_data/` (infrastructure DTOs)

### MIGRATE (domain dataclass → Pydantic)
- `Bar`, `SyncStatus` (entities)
- `SymbolAggregate`, `OHLCVAggregate`, `QuoteAggregate` (aggregates)
- `OrderAggregate`, `PositionAggregate` (aggregates)

### KEEP AS-IS
- Domain events (`DomainEvent`, all children) — frozen dataclasses, not persisted
- Value objects (`Symbol`, `SymbolInfo`, `PnL`, `Price`, `OHLCV` VO, `BarRange`, etc.) — frozen dataclasses
- `BacktestResult`, `OptimizationResult` — application models, separate concern
- Enums — stay as-is

## Risk Mitigation

- Compile check (`ruff check src/ && pyright src/`) after each phase
- Run `pytest` after each phase
- One commit per phase for easy rollback
