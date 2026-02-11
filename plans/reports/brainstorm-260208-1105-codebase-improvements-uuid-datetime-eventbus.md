# Brainstorm: Codebase Improvements

**Date:** 2026-02-08 | **Type:** Technical Debt Reduction
**Status:** Analysis Complete | **Items:** 4

---

## Executive Summary

| Item | Current State | Recommendation | Effort |
|------|--------------|----------------|--------|
| 1. UUID Format | UUID v4 (stdlib) | **Migrate to UUID v7** (Python 3.14 native) | Medium |
| 2. Datetime Naming | Mixed (`occurred_at`, `timestamp`, etc.) | **Standardize to `created_at`/`updated_at`** | Low |
| 3. Event Handler Registration | Manual `subscribe()` calls | **Decorator-based auto-discovery** | Medium |
| 4. EventBus Coroutine Handling | `inspect.iscoroutine()` check | **Current approach is fine** | None |

---

## Item 1: UUID v4 → UUID v7 Migration

### Current State
- 12 files using `uuid4()` from stdlib
- Mixed usage: `UUID` type (aggregates) vs `str` type with conversion
- All DomainEvents use `event_id: UUID`

### Research Findings

| Feature | UUID v4 | UUID v7 | ULID |
|---------|---------|---------|------|
| Sortable | No | Yes (time-ordered) | Yes |
| Standard | RFC 9562 | RFC 9562 (2024) | De facto only |
| Python Native | Yes (all versions) | **Yes (3.14+)** | No (3rd party) |
| DB Performance | Poor (random inserts) | **Excellent** | Excellent |

### Recommendation: **UUID v7**

**Why UUID v7 over ULID:**
1. **Python 3.14 native support** - `uuid.uuid7()` is built-in
2. **RFC standardized** - Better ecosystem compatibility
3. **PostgreSQL UUID type** - Works natively
4. **Time-ordered** - Better B-tree index performance

**Trade-offs:**
- Timestamps embedded in UUID (acceptable for internal IDs)
- Requires Python 3.14+ (already on this version)

### Migration Steps
1. Create `src/common/uuid.py` module with `generate_id() -> UUID`
2. Replace all `uuid4()` calls with `uuid7()`
3. Standardize on `UUID` type everywhere
4. Update Pydantic models' default_factory

---

## Item 2: Datetime Property Naming Standardization

### Current State
| Pattern | Usage | Files |
|---------|-------|-------|
| `created_at` | Record creation time | Order, OHLCV sync |
| `updated_at` | Last modification | Order aggregate |
| `occurred_at` | Domain event time | All DomainEvents |
| `timestamp` | Temporal data point | Quote, OHLCV bar |
| `last_update` | Last refresh time | Quote aggregate |

### Recommendation: **Minimal Changes**

1. **Keep `occurred_at`** for DomainEvents - semantically correct
2. **Keep `timestamp`** for market data - standard financial term
3. **Rename only `last_update` → `updated_at`** in QuoteAggregate

---

## Item 3: Auto-Discovery Event Handler Registration

### Current State
Manual subscription scattered across 11 files:
```python
event_bus.subscribe(QuoteEvent, self._handle_quote)
```

### Recommendation: **Decorator Registry Pattern**

```python
@event_handler(QuoteEvent)
async def _handle_quote(self, event: QuoteEvent) -> None:
    ...
```

**Bootstrap:**
```python
async def register_event_handlers(event_bus: EventBus):
    for event_type, handlers in get_handlers().items():
        for handler in handlers:
            event_bus.subscribe(event_type, handler)
```

---

## Item 4: EventBus Coroutine Handling

### Current Implementation
```python
async def publish(self, event: DomainEvent) -> None:
    for handler in handlers:
        result = handler(event)
        if inspect.iscoroutine(result):
            await result
```

### Recommendation: **No Changes Needed**

Current `inspect.iscoroutine(result)` pattern is idiomatic and correct for Python 3.14.

---

## Implementation Priority

| Order | Item | Effort | Impact |
|-------|------|--------|--------|
| 1 | UUID v7 Migration | Medium | High (DB perf) |
| 2 | Event Auto-Discovery | Medium | Medium (DX) |
| 3 | Datetime Rename | Low | Low |
| 4 | EventBus Coroutine | None | N/A |

---

## Sources
- [UUID v4 vs v7 vs ULID](https://medium.com/@ciro-gomes-dev/uuidv4-vs-uuidv7-vs-ulid-choosing-the-right-identifier-for-database-performance-1f7d1a0fe0ba)
- [Python 3.14 uuid docs](https://docs.python.org/3/library/uuid.html)
- [Python 3.14 asyncio changes](https://blog.changs.co.uk/python-314-3-asyncio-changes.html)
