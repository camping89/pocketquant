# Phase 2: Delete QuoteAggregate

## Overview
- **Priority**: HIGH
- **Status**: pending

## Context
- `src/domain/quote/aggregate.py` — `QuoteAggregate` (Pydantic, in-memory only)
- **Zero instantiations** in entire codebase — dead code
- `Quote` DTO in `src/application/market_data/quote_dto.py` does all real work
- `QuoteReceivedEvent` and `QuoteUpdatedEvent` are consumed by `StrategyAppService` but never published (real-time gap — addressed in Phase 4)

## Key Check Before Delete
- `QuoteReceivedEvent` and `QuoteUpdatedEvent` — keep the event classes (they're consumed)
- Only delete the aggregate that was supposed to emit them

## Files to Modify

| File | Action |
|------|--------|
| `src/domain/quote/__init__.py` | Remove `QuoteAggregate` export |

## Files to Delete

| File | Reason |
|------|--------|
| `src/domain/quote/aggregate.py` | Dead code — zero instantiations |

## Implementation Steps

### 1. Verify zero usages
```bash
rg "QuoteAggregate" src/
```
Should only find: `aggregate.py` itself and `__init__.py` export.

### 2. Update `src/domain/quote/__init__.py`
- Remove `from src.domain.quote.aggregate import QuoteAggregate`
- Remove `QuoteAggregate` from `__all__`

### 3. Delete `src/domain/quote/aggregate.py`

### 4. Verify no broken imports
```bash
rg "QuoteAggregate" src/
```

### 5. Compile check + test

## Success Criteria

- [ ] `QuoteAggregate` class deleted
- [ ] No imports referencing `QuoteAggregate` anywhere
- [ ] `QuoteReceivedEvent` and `QuoteUpdatedEvent` still importable (kept in `quote_event.py`)
- [ ] All tests pass
