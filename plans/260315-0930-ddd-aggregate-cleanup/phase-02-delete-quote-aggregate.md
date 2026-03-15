# Phase 2: Delete QuoteAggregate

## Overview
- **Priority**: HIGH
- **Status**: pending

## Context
- `src/domain/quote/aggregate.py` — `QuoteAggregate` (Pydantic, in-memory only)
- **Zero instantiations** in entire codebase — dead code
- `QuoteReceivedEvent` and `QuoteUpdatedEvent` — keep dead (not wired). App focuses on bar-completed processing.
- `StrategyAppService._on_quote_received()` handler — keep dead (trigger="tick" path preserved for future use)

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

### 4. Add TODO to README
Add note under Features or a TODO section:
```
<!-- TODO: Revisit tick-triggered strategy support (QuoteReceivedEvent wiring) when needed -->
```

### 5. Verify no broken imports
```bash
rg "QuoteAggregate" src/
```

### 6. Compile check + test

## Success Criteria

- [ ] `QuoteAggregate` class deleted
- [ ] No imports referencing `QuoteAggregate` anywhere
- [ ] `QuoteReceivedEvent` and `QuoteUpdatedEvent` still importable (kept in `quote_event.py`)
- [ ] `StrategyAppService._on_quote_received()` handler preserved (dead but intact)
- [ ] TODO added to README for future tick-triggered strategy revision
- [ ] All tests pass
