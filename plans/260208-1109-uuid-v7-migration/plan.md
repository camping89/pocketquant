---
title: "UUID v7 Migration"
description: "Migrate from uuid4() to uuid7() with centralized generate_id() wrapper"
status: complete
priority: P2
effort: 2h
branch: feat/strategy-init
tags: [refactor, uuid, performance]
created: 2026-02-08
---

# UUID v7 Migration Plan

## Overview

Migrate from `uuid4()` (random) to `uuid7()` (time-ordered) across codebase. Python 3.14 provides native `uuid7()` support.

**Benefits:**
- Time-ordered: natural chronological sorting
- Better DB indexing performance (B-tree friendly)
- Preserves randomness for uniqueness

## Current State

12 source files use `uuid4()`:
- 4 domain aggregates (Pydantic `Field(default_factory=uuid4)`)
- 1 domain entity (dataclass `field(default_factory=uuid4)`)
- 1 domain event base class
- 2 infrastructure files (tracing)
- 4 feature files (backtesting, brokers)

**Mixed typing:** Some use `UUID`, others use `str` for IDs.

## Phases

| Phase | Description | Status | Effort |
|-------|-------------|--------|--------|
| [Phase 1](./phase-01-create-uuid-module.md) | Create wrapper module | pending | 20m |
| [Phase 2](./phase-02-migrate-domain-events.md) | Migrate domain events | pending | 30m |
| [Phase 3](./phase-03-migrate-aggregates.md) | Migrate aggregates & entities | pending | 40m |
| [Phase 4](./phase-04-update-tests.md) | Update tests & verify | pending | 30m |

## Key Decisions

1. **Wrapper module:** `src/common/uuid.py` with `generate_id() -> UUID`
2. **Standardize on `UUID` type:** Replace `str(uuid4())` with `str(generate_id())`
3. **Backward compatible:** No schema changes, UUID v7 is still valid UUID format

## Files to Modify

### Domain Layer (5 files)
- `src/domain/shared/domain_event.py`
- `src/domain/symbol/aggregate.py`
- `src/domain/ohlcv/aggregate.py`
- `src/domain/ohlcv/entities.py`
- `src/domain/quote/aggregate.py`

### Infrastructure Layer (4 files)
- `src/common/tracing/context.py`
- `src/common/tracing/correlation.py`
- `src/domain/order/aggregate.py`
- `src/domain/position/aggregate.py`

### Features Layer (3 files)
- `src/features/backtesting/engine/backtest_runner.py`
- `src/features/backtesting/optimizer/grid_optimizer.py`
- `src/infrastructure/brokers/paper/paper_broker.py`

## Success Criteria

- [ ] All `uuid4()` replaced with `generate_id()`
- [ ] All tests pass
- [ ] Type checking passes (pyright)
- [ ] No runtime errors
