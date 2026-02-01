# Phase 5: Convert Domain Layer to Pydantic

## Context

- Parent: [plan.md](plan.md)
- Depends on: Phases 1-4

## Overview

- **Priority:** P1
- **Status:** pending
- **Effort:** 45m

Convert all domain layer classes (aggregates, value objects, events) from dataclass to Pydantic.

## Philosophy Change

**Before (academic DDD):**
- Domain = pure Python dataclass (no frameworks)
- Persistence = separate Pydantic models
- Two classes for same concept

**After (pragmatic, like .NET):**
- Domain entity = Pydantic model with business methods
- Same class used for persistence
- One class for same concept

## Files to Modify

### Value Objects (frozen=True)

| File | Classes |
|------|---------|
| `src/domain/shared/value_objects.py` | Interval, Symbol, Price, BarRange |
| `src/domain/ohlcv/value_objects.py` | OHLCV bar types |
| `src/domain/order/value_objects.py` | OrderSide, OrderType, OrderStatus |
| `src/domain/position/value_objects.py` | PositionSide, PnL |

### Aggregates (mutable with business logic)

| File | Classes |
|------|---------|
| `src/domain/ohlcv/aggregate.py` | OHLCVAggregate |
| `src/domain/order/aggregate.py` | OrderAggregate |
| `src/domain/position/aggregate.py` | PositionAggregate |
| `src/domain/quote/aggregate.py` | QuoteAggregate |

### Domain Events (frozen=True)

| File | Classes |
|------|---------|
| `src/domain/ohlcv/events.py` | HistoricalDataSyncedEvent, BarCompletedEvent |
| `src/domain/order/events.py` | OrderSubmittedEvent, OrderFilledEvent, etc |
| `src/domain/position/events.py` | PositionOpenedEvent, PositionClosedEvent |

## Implementation Pattern

### Value Object (immutable)

Before:
```python
@dataclass(frozen=True)
class Interval:
    value: str

    def __post_init__(self):
        if self.value not in VALID_INTERVALS:
            raise ValueError(f"Invalid: {self.value}")
```

After:
```python
class Interval(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: str

    @field_validator("value")
    @classmethod
    def validate_interval(cls, v: str) -> str:
        if v not in VALID_INTERVALS:
            raise ValueError(f"Invalid: {v}")
        return v
```

### Aggregate (mutable)

Before:
```python
@dataclass
class OrderAggregate:
    order_id: str
    status: OrderStatus = OrderStatus.PENDING
    _events: list = field(default_factory=list)

    def submit(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise ValueError("...")
        self.status = OrderStatus.SUBMITTED
        self._events.append(OrderSubmittedEvent(...))
```

After:
```python
class OrderAggregate(BaseModel):
    order_id: str
    status: OrderStatus = OrderStatus.PENDING
    _events: list = PrivateAttr(default_factory=list)

    def submit(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise ValueError("...")
        self.status = OrderStatus.SUBMITTED
        self._events.append(OrderSubmittedEvent(...))

    def to_mongo(self) -> dict:
        return self.model_dump()
```

### Domain Event (immutable)

Before:
```python
@dataclass(frozen=True)
class OrderSubmittedEvent:
    order_id: str
    submitted_at: datetime
```

After:
```python
class OrderSubmittedEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    submitted_at: datetime
```

## Todo

- [ ] Convert value objects in src/domain/shared/
- [ ] Convert value objects in each domain subdirectory
- [ ] Convert aggregates (add PrivateAttr for _events)
- [ ] Convert domain events
- [ ] Update imports in handlers
- [ ] Remove test_domain_purity.py (no longer applicable)
- [ ] Run pyright

## Success Criteria

- [ ] All value objects are frozen Pydantic models
- [ ] All aggregates are Pydantic with business methods
- [ ] All events are frozen Pydantic models
- [ ] PrivateAttr used for internal state (_events)
- [ ] No dataclass imports in domain layer
- [ ] All tests pass

## Notes

- Use `PrivateAttr` for fields that shouldn't be in model_dump()
- Use `ConfigDict(frozen=True)` for immutability
- Keep business methods in the model classes
- Validation moves from `__post_init__` to `@field_validator`
