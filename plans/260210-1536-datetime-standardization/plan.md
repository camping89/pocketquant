---
title: "Datetime Property Standardization in QuoteAggregate"
description: "Rename last_update → updated_at in QuoteAggregate for consistency with DDD naming conventions"
status: complete
priority: P3
effort: 0.5h
branch: feat/strategy-init
tags: [refactoring, domain-model, datetime-standardization]
created: 2026-02-10
---

## Summary

Standardize datetime property naming in the QuoteAggregate root to follow DDD conventions. Only `last_update` will be renamed to `updated_at`. Other datetime properties remain unchanged:
- `occurred_at`: Kept for DomainEvents (semantic: when event occurred)
- `timestamp`: Kept for market data (semantic: data timestamp)
- `updated_at`: NEW in QuoteAggregate (replacing `last_update`)

## Context

The current QuoteAggregate uses `last_update` which is inconsistent with DDD naming standards. The standardization follows:
- **Domain Events** use `occurred_at` (semantic: when did this event happen)
- **Market Data** uses `timestamp` (semantic: price/volume timestamp)
- **Aggregate State** uses `updated_at` (semantic: when was this aggregate last modified)

## Scope

**Single file change:**
- `src/domain/quote/aggregate.py`

**Impact:**
- 2 locations: property definition (line 26) + assignment (line 64)
- No breaking changes to public API (QuoteAggregate is internal domain model)
- No database migration needed (MongoDB field will be created fresh)

## Implementation

### File: src/domain/quote/aggregate.py

**Before:**
```python
class QuoteAggregate(BaseModel):
    """Aggregate root for real-time quote management."""

    id: UUID = Field(default_factory=uuid4)
    symbol: str = ""
    exchange: str = ""
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    change: float | None = None
    change_percent: float | None = None
    last_update: datetime | None = None  # ← RENAME TO updated_at
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    # ...

    def update_from_tick(
        self,
        price: float,
        volume: float | None = None,
        bid: float | None = None,
        ask: float | None = None,
        change: float | None = None,
        change_percent: float | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Update quote from incoming tick data."""
        self.last_price = price
        if volume is not None:
            self.volume = volume
        if bid is not None:
            self.bid = bid
        if ask is not None:
            self.ask = ask
        if change is not None:
            self.change = change
        if change_percent is not None:
            self.change_percent = change_percent
        self.last_update = timestamp  # ← RENAME TO updated_at
        # ...
```

**After:**
```python
class QuoteAggregate(BaseModel):
    """Aggregate root for real-time quote management."""

    id: UUID = Field(default_factory=uuid4)
    symbol: str = ""
    exchange: str = ""
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    change: float | None = None
    change_percent: float | None = None
    updated_at: datetime | None = None  # ✓ RENAMED
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    # ...

    def update_from_tick(
        self,
        price: float,
        volume: float | None = None,
        bid: float | None = None,
        ask: float | None = None,
        change: float | None = None,
        change_percent: float | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Update quote from incoming tick data."""
        self.last_price = price
        if volume is not None:
            self.volume = volume
        if bid is not None:
            self.bid = bid
        if ask is not None:
            self.ask = ask
        if change is not None:
            self.change = change
        if change_percent is not None:
            self.change_percent = change_percent
        self.updated_at = timestamp  # ✓ RENAMED
        # ...
```

## Success Criteria

- [ ] Property renamed in line 26: `last_update` → `updated_at`
- [ ] Assignment renamed in line 64: `self.last_update` → `self.updated_at`
- [ ] File compiles without errors
- [ ] Type checking passes (pyright)
- [ ] Tests pass (QuoteAggregate tests + all dependent tests)
- [ ] Code reviewed and merged

## Testing

Run these after implementation:

```bash
# Type checking
pyright src/domain/quote/aggregate.py

# Unit tests (QuoteAggregate + quote event tests)
pytest tests/domain/quote/test_quote_aggregate.py -v

# Full test suite
pytest tests/ -v

# Linting
ruff check src/domain/quote/aggregate.py
```

## Related Files

- `src/domain/quote/quote_event.py` - QuoteReceivedEvent, QuoteUpdatedEvent (no changes)
- `src/domain/shared/domain_event.py` - Base DomainEvent (no changes)
- `tests/domain/quote/test_quote_aggregate.py` - Update assertions if any reference `last_update`

## Dependencies

None. Standalone change with no upstream/downstream service dependencies.

## Rollback

If needed, revert to `last_update` with a single commit.

---

**Notes:**
- This is a pure refactoring with no functional changes
- Aligns QuoteAggregate naming with DDD best practices
- Enables future standardization across other aggregates if needed
