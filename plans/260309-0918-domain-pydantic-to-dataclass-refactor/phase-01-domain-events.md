# Phase 1: Domain Events -> @dataclass(frozen=True)

## Overview
- **Priority:** High (fewest dependencies, foundation for other phases)
- **Status:** completed
- **Effort:** 30min

Easiest phase. Events are simple frozen data holders. No validators, no methods beyond `__eq__`/`__hash__` on base class.

## Files to Modify

| File | Classes | LOC |
|------|---------|-----|
| `src/domain/shared/domain_event.py` | `DomainEvent` | 25 |
| `src/domain/order/order_event.py` | 5 event classes | 55 |
| `src/domain/position/position_event.py` | 3 event classes | 41 |
| `src/domain/quote/quote_event.py` | 2 event classes | 26 |
| `src/domain/ohlcv/ohlcv_event.py` | 2 event classes | 32 |
| `src/domain/strategy/strategy_event.py` | 1 event class | 18 |

## Conversion: DomainEvent Base

```python
# BEFORE: src/domain/shared/domain_event.py
from pydantic import BaseModel, ConfigDict, Field
from src.common.uuid import UUID, generate_id

class DomainEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID = Field(default_factory=generate_id)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DomainEvent):
            return NotImplemented
        return self.event_id == other.event_id

    def __hash__(self) -> int:
        return hash(self.event_id)
```

```python
# AFTER: src/domain/shared/domain_event.py
from dataclasses import dataclass, field
from src.common.uuid import UUID, generate_id

@dataclass(frozen=True, eq=False)
class DomainEvent:
    """Base class for all domain events."""
    event_id: UUID = field(default_factory=generate_id)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DomainEvent):
            return NotImplemented
        return self.event_id == other.event_id

    def __hash__(self) -> int:
        return hash(self.event_id)
```

**Key:** `eq=False` so we keep custom `__eq__`/`__hash__` (frozen=True alone would auto-generate eq based on ALL fields, which we don't want -- we compare by event_id only).

## Conversion: Child Events

All child events follow identical pattern. Example:

```python
# BEFORE: src/domain/order/order_event.py
from src.domain.shared.domain_event import DomainEvent

class OrderSubmittedEvent(DomainEvent):
    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float | None = None
```

```python
# AFTER: src/domain/order/order_event.py
from dataclasses import dataclass
from src.domain.shared.domain_event import DomainEvent

@dataclass(frozen=True, eq=False)
class OrderSubmittedEvent(DomainEvent):
    """Event raised when an order is submitted to broker."""
    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float | None = None
```

**Pattern for ALL child events:**
1. Remove `from pydantic import ...`
2. Add `from dataclasses import dataclass`
3. Add `@dataclass(frozen=True, eq=False)` decorator
4. Fields stay identical (defaults already stdlib-compatible)

## Frozen Inheritance Note

Python dataclass inheritance requires ALL classes in chain to be frozen if any is frozen. Since `DomainEvent` is `frozen=True`, all children MUST also be `frozen=True`. This is already our intent.

## Implementation Steps

1. Convert `src/domain/shared/domain_event.py`
2. Convert `src/domain/order/order_event.py` (5 classes)
3. Convert `src/domain/position/position_event.py` (3 classes)
4. Convert `src/domain/quote/quote_event.py` (2 classes)
5. Convert `src/domain/ohlcv/ohlcv_event.py` (2 classes)
6. Convert `src/domain/strategy/strategy_event.py` (1 class)
7. Run `ruff check src/domain/` and `pyright src/domain/`

## Todo

- [x] Convert DomainEvent base class
- [x] Convert order events (5)
- [x] Convert position events (3)
- [x] Convert quote events (2)
- [x] Convert ohlcv events (2)
- [x] Convert strategy events (1)
- [x] Lint + type check pass

## Success Criteria
- All 14 event classes are `@dataclass(frozen=True, eq=False)`
- Zero Pydantic imports in event files
- `ruff check` and `pyright` pass on domain/
- Aggregate tests still pass (events created in aggregate methods)
