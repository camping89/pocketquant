# Phase 3: Aggregates -> @dataclass (mutable)

## Overview
- **Priority:** High (core of the refactor)
- **Status:** completed
- **Effort:** 45min

Hardest phase. Aggregates are mutable state machines with `PrivateAttr(_events)`, `Field(default_factory=...)`, `ClassVar`, and factory methods. NOT frozen -- they mutate state via methods like `submit()`, `fill()`, `close()`.

## Files to Modify

| File | Class | LOC | Complexity |
|------|-------|-----|------------|
| `src/domain/order/aggregate.py` | `OrderAggregate` | 227 | High -- state machine, ClassVar transitions |
| `src/domain/position/aggregate.py` | `PositionAggregate` | 201 | High -- P&L calc, scale in/out |
| `src/domain/symbol/aggregate.py` | `SymbolAggregate` | 93 | Low -- simple CRUD |
| `src/domain/quote/aggregate.py` | `QuoteAggregate` | 98 | Low -- tick updates |
| `src/domain/ohlcv/aggregate.py` | `OHLCVAggregate` | 87 | Low -- event recording |

## Key Conversion Pattern: PrivateAttr -> field(init=False)

All 5 aggregates use `PrivateAttr(default_factory=list)` for `_events`. Dataclass equivalent:

```python
# BEFORE (Pydantic)
from pydantic import BaseModel, PrivateAttr
class OrderAggregate(BaseModel):
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

# AFTER (dataclass)
from dataclasses import dataclass, field
@dataclass
class OrderAggregate:
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)
```

**`init=False`**: not a constructor arg (like PrivateAttr)
**`repr=False`**: excluded from repr (like PrivateAttr)

## Conversion: OrderAggregate (most complex)

```python
# AFTER: src/domain/order/aggregate.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

from src.common.uuid import generate_id_str
from src.domain.order.order_event import (
    OrderCancelledEvent, OrderFilledEvent, OrderPartiallyFilledEvent,
    OrderRejectedEvent, OrderSubmittedEvent,
)
from src.domain.order.value_objects import OrderSide, OrderStatus, OrderType
from src.domain.shared.domain_event import DomainEvent


class InvalidOrderTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


@dataclass
class OrderAggregate:
    """Order aggregate root with state machine."""

    id: str
    strategy_id: str
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: float | None = None
    broker_order_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    # State machine: valid transitions (class-level)
    _VALID_TRANSITIONS: ClassVar[dict[OrderStatus, frozenset[OrderStatus]]] = {
        OrderStatus.PENDING: frozenset({OrderStatus.SUBMITTED, OrderStatus.REJECTED}),
        OrderStatus.SUBMITTED: frozenset(
            {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED}
        ),
        OrderStatus.PARTIALLY_FILLED: frozenset(
            {OrderStatus.FILLED, OrderStatus.CANCELLED}
        ),
    }

    # All methods (create, submit, fill, partial_fill, cancel, reject,
    # _validate_transition, collect_events, remaining_quantity) stay IDENTICAL.
    # No body changes needed -- only class declaration + field syntax changes.
```

**What changes:**
1. `BaseModel` -> `@dataclass`
2. `Field(default_factory=...)` -> `field(default_factory=...)`
3. `PrivateAttr(default_factory=list)` -> `field(default_factory=list, init=False, repr=False)`
4. Remove `from pydantic import BaseModel, Field, PrivateAttr`
5. Add `from dataclasses import dataclass, field`

**What stays identical:**
- `@classmethod def create(...)` factory method
- All state mutation methods (`submit`, `fill`, `partial_fill`, `cancel`, `reject`)
- `_VALID_TRANSITIONS` ClassVar
- `_validate_transition` method
- `collect_events` method
- `remaining_quantity` property

**ClassVar note:** `ClassVar` works identically in dataclasses. Dataclasses explicitly skip `ClassVar` fields.

## Conversion: PositionAggregate

Same pattern as OrderAggregate:

```python
@dataclass
class PositionAggregate:
    """Position aggregate root tracking entry, quantity, and P&L."""

    id: str
    strategy_id: str
    symbol: str
    exchange: str
    side: PositionSide
    entry_price: float
    quantity: float
    current_price: float
    realized_pnl: float = 0.0
    is_closed: bool = False
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    # All methods stay identical: open(), update_price(), add_quantity(),
    # reduce_quantity(), close(), _close(), _calculate_pnl_per_unit(),
    # unrealized_pnl, pnl, market_value, cost_basis, collect_events()
```

## Conversion: SymbolAggregate

```python
@dataclass(eq=False)
class SymbolAggregate:
    """Aggregate root for symbol management."""

    id: UUID = field(default_factory=generate_id)
    info: SymbolInfo | None = None
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SymbolAggregate):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    # create(), deactivate(), activate(), properties, event methods stay identical
```

**Note:** `eq=False` because custom `__eq__`/`__hash__` defined. Same approach for QuoteAggregate and OHLCVAggregate.

## Conversion: QuoteAggregate

```python
@dataclass(eq=False)
class QuoteAggregate:
    """Aggregate root for real-time quote management."""

    id: UUID = field(default_factory=generate_id)
    symbol: str = ""
    exchange: str = ""
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    change: float | None = None
    change_percent: float | None = None
    updated_at: datetime | None = None
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    # __eq__, __hash__, create(), update_from_tick(), mark_updated(),
    # symbol_key, get_uncommitted_events(), clear_events() stay identical
```

## Conversion: OHLCVAggregate

```python
@dataclass(eq=False)
class OHLCVAggregate:
    """Aggregate root for OHLCV data operations."""

    id: UUID = field(default_factory=generate_id)
    symbol: str = ""
    exchange: str = ""
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    # __eq__, __hash__, create(), record_sync(), record_bar_completed(),
    # get_uncommitted_events(), clear_events() stay identical
```

## Impact on Document.to_aggregate()

Persistence schemas create aggregates via constructor kwargs:

```python
# OrderDocument.to_aggregate() -- NO CHANGE NEEDED
def to_aggregate(self) -> OrderAggregate:
    return OrderAggregate(
        id=self.id,
        strategy_id=self.strategy_id,
        side=OrderSide(self.side),  # explicit enum conversion already done
        ...
    )
```

Dataclass constructor accepts same kwargs. `_events` is `init=False` so not passed (same as PrivateAttr wasn't passed). Works identically.

## Implementation Steps

1. Convert `src/domain/order/aggregate.py` (OrderAggregate)
2. Convert `src/domain/position/aggregate.py` (PositionAggregate)
3. Convert `src/domain/symbol/aggregate.py` (SymbolAggregate)
4. Convert `src/domain/quote/aggregate.py` (QuoteAggregate)
5. Convert `src/domain/ohlcv/aggregate.py` (OHLCVAggregate)
6. Run `ruff check src/domain/` and `pyright src/domain/`

## Todo

- [x] Convert OrderAggregate (state machine + ClassVar)
- [x] Convert PositionAggregate (P&L + scale in/out)
- [x] Convert SymbolAggregate (simple, eq=False)
- [x] Convert QuoteAggregate (simple, eq=False)
- [x] Convert OHLCVAggregate (simple, eq=False)
- [x] Lint + type check pass

## Success Criteria
- All 5 aggregates are `@dataclass` (NOT frozen)
- `_events` uses `field(default_factory=list, init=False, repr=False)`
- `ClassVar` fields still work
- Factory methods (`create`, `open`) still work
- State mutation methods unchanged
- `Document.to_aggregate()` still works (constructor kwargs identical)
- `ruff check` and `pyright` pass
