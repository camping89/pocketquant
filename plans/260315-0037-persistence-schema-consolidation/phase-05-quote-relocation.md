# Phase 5: Quote Schema Relocation

## Overview
- **Priority**: MEDIUM
- **Status**: completed

## Context
- Current schema: `src/persistence/schemas/quote_schema.py` — `Quote`, `QuoteTick`, `AggregatedBar`, `QuoteSubscription`
- Current aggregate: `src/domain/quote/aggregate.py` — `QuoteAggregate` (dataclass)
- No quote MongoDB repo — quotes go to Redis cache

## Key Insight

Quote schemas are NOT MongoDB document models. They're:
- `Quote` — Redis cache DTO (used by `quote_app_service.py`, handlers)
- `QuoteTick` — tick data DTO (used by `bar_app_service.py`, `quote_app_service.py`)
- `AggregatedBar` — bar aggregation DTO (used by `bar_app_service.py`)
- `QuoteSubscription` — subscription DTO (used by app services)

These are **application-layer DTOs**, not persistence schemas. Relocate them.

`QuoteAggregate` has no repo, no persistence. It's in-memory only. Still migrate to Pydantic for consistency.

## Files to Modify

| File | Action |
|------|--------|
| `src/domain/quote/aggregate.py` | Migrate `QuoteAggregate` dataclass → Pydantic |
| `src/application/market_data/quote_app_service.py` | Update import path |
| `src/application/market_data/bar_app_service.py` | Update import path |
| `src/features/market_data/quotes/get_all/handler.py` | Update import path |
| `src/features/market_data/quotes/get_latest/handler.py` | Update import path |
| `src/features/market_data/quotes/dto.py` | Update import path |
| `src/domain/quote/__init__.py` | Update exports |

## Files to Create
| File | Content |
|------|---------|
| `src/application/market_data/quote_dto.py` | `Quote`, `QuoteTick`, `AggregatedBar`, `QuoteSubscription` (moved from schema) |

## Files to Delete
| File | Reason |
|------|--------|
| `src/persistence/schemas/quote_schema.py` | Content relocated |

## Implementation Steps

### 1. Create `src/application/market_data/quote_dto.py`

Move all 4 classes from `quote_schema.py` verbatim. No logic changes — just a new home.

### 2. Migrate `QuoteAggregate` (dataclass → Pydantic)

```python
class QuoteAggregate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    symbol: str = ""
    exchange: str = ""
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    change: float | None = None
    change_percent: float | None = None
    updated_at: datetime | None = None
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    # ... existing methods stay
```

No `to_mongo()`/`from_mongo()` needed — QuoteAggregate is not persisted to MongoDB.

### 3. Update all imports

Find-replace `from src.persistence.schemas.quote_schema import` → `from src.application.market_data.quote_dto import`

### 4. Delete `src/persistence/schemas/quote_schema.py`

### 5. Compile check + test

## Success Criteria

- [x] `QuoteAggregate` is Pydantic BaseModel
- [x] Quote DTOs relocated to `src/application/market_data/quote_dto.py`
- [x] No imports from `src.persistence.schemas.quote_schema`
- [x] `quote_schema.py` deleted
- [x] All tests pass
