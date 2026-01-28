# Phase 3: Domain Layer

## Context Links
- Parent: [plan.md](plan.md)
- Blocked by: [Phase 2](phase-02-infrastructure-layer.md)
- Research: [DDD Patterns](research/researcher-ddd-cqrs-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-27 |
| Priority | P1 |
| Status | completed |
| Effort | 3h |

Create pure domain layer with aggregates, entities, value objects, and domain events. **CRITICAL:** Domain layer MUST have ZERO I/O imports.

## Key Insights

From DDD research:
- **Value Objects:** `@dataclass(frozen=True)` - immutable, equality by value
- **Entities:** `@dataclass(eq=False)` - identity-based equality
- **Aggregates:** Root entity + collected events
- **Domain Events:** Immutable records of state changes

Current `BarManager` already follows pure domain patterns (no I/O).

## Requirements

### Functional
- Aggregate roots with event collection
- Value objects for Symbol, Interval, Price concepts
- Domain events for state changes
- Domain services for complex logic

### Non-Functional
- Zero imports from infrastructure
- No async I/O in domain layer
- Hashable value objects for caching

## Architecture

```
src/domain/
├── __init__.py
├── shared/
│   ├── __init__.py
│   ├── value_objects.py      # Symbol, Exchange, Interval
│   └── events.py             # Base DomainEvent class
├── ohlcv/
│   ├── __init__.py
│   ├── aggregate.py          # OHLCVAggregate root
│   ├── entities.py           # Bar entity
│   ├── value_objects.py      # OHLCV-specific VOs
│   ├── events.py             # HistoricalDataSynced, BarCompleted
│   └── services/
│       └── bar_builder.py    # Pure bar aggregation (from BarManager)
├── symbol/
│   ├── __init__.py
│   ├── aggregate.py          # SymbolAggregate
│   └── value_objects.py      # SymbolInfo
└── quote/
    ├── __init__.py
    ├── aggregate.py          # QuoteAggregate
    ├── value_objects.py      # QuoteTick, Price
    └── events.py             # QuoteReceived, QuoteUpdated
```

## Related Code Files

### Create
- `src/domain/__init__.py`
- `src/domain/shared/__init__.py`
- `src/domain/shared/value_objects.py`
- `src/domain/shared/events.py`
- `src/domain/ohlcv/__init__.py`
- `src/domain/ohlcv/aggregate.py`
- `src/domain/ohlcv/entities.py`
- `src/domain/ohlcv/value_objects.py`
- `src/domain/ohlcv/events.py`
- `src/domain/ohlcv/services/bar_builder.py`
- `src/domain/symbol/__init__.py`
- `src/domain/symbol/aggregate.py`
- `src/domain/symbol/value_objects.py`
- `src/domain/quote/__init__.py`
- `src/domain/quote/aggregate.py`
- `src/domain/quote/value_objects.py`
- `src/domain/quote/events.py`

### Modify
- `src/features/market_data/managers/bar_manager.py` - Extract pure logic to domain

## Implementation Steps

1. **Create shared domain primitives**
   ```python
   # src/domain/shared/value_objects.py
   from dataclasses import dataclass
   from enum import Enum

   @dataclass(frozen=True)
   class Symbol:
       """Value object - immutable, equality by value"""
       code: str
       exchange: str

       def __post_init__(self):
           if not self.code:
               raise ValueError("Symbol code required")
           if not self.exchange:
               raise ValueError("Exchange required")

       def __str__(self) -> str:
           return f"{self.exchange}:{self.code}"

   class Interval(str, Enum):
       ONE_MIN = "1m"
       FIVE_MIN = "5m"
       FIFTEEN_MIN = "15m"
       ONE_HOUR = "1h"
       FOUR_HOUR = "4h"
       ONE_DAY = "1d"
       ONE_WEEK = "1w"
       ONE_MONTH = "1M"
   ```

2. **Create base domain event**
   ```python
   # src/domain/shared/events.py
   from dataclasses import dataclass
   from datetime import datetime
   from uuid import UUID

   @dataclass(frozen=True)
   class DomainEvent:
       aggregate_id: UUID
       occurred_at: datetime

       def __eq__(self, other):
           return (
               isinstance(other, self.__class__) and
               self.aggregate_id == other.aggregate_id and
               self.occurred_at == other.occurred_at
           )
   ```

3. **Create OHLCV aggregate with events**
   ```python
   # src/domain/ohlcv/aggregate.py
   from dataclasses import dataclass, field
   from uuid import UUID, uuid4
   from datetime import datetime
   from typing import List
   from src.domain.shared.events import DomainEvent
   from src.domain.ohlcv.events import HistoricalDataSynced

   @dataclass(eq=False)
   class OHLCVAggregate:
       id: UUID = field(default_factory=uuid4)
       symbol: str = ""
       exchange: str = ""
       _events: List[DomainEvent] = field(default_factory=list)

       def __eq__(self, other):
           if not isinstance(other, OHLCVAggregate):
               return False
           return self.id == other.id

       def __hash__(self):
           return hash(self.id)

       def record_sync(self, interval: str, n_bars: int, last_ts: int):
           event = HistoricalDataSynced(
               aggregate_id=self.id,
               occurred_at=datetime.utcnow(),
               symbol=self.symbol,
               exchange=self.exchange,
               interval=interval,
               n_bars=n_bars,
               last_timestamp=last_ts
           )
           self._events.append(event)

       def get_uncommitted_events(self) -> List[DomainEvent]:
           return self._events.copy()

       def clear_events(self):
           self._events.clear()
   ```

4. **Create OHLCV domain events**
   ```python
   # src/domain/ohlcv/events.py
   from dataclasses import dataclass
   from src.domain.shared.events import DomainEvent

   @dataclass(frozen=True)
   class HistoricalDataSynced(DomainEvent):
       symbol: str = ""
       exchange: str = ""
       interval: str = ""
       n_bars: int = 0
       last_timestamp: int = 0

   @dataclass(frozen=True)
   class BarCompleted(DomainEvent):
       symbol: str = ""
       exchange: str = ""
       interval: str = ""
       open: float = 0.0
       high: float = 0.0
       low: float = 0.0
       close: float = 0.0
       volume: float = 0.0
       timestamp: int = 0
   ```

5. **Extract BarManager logic to domain service**
   - Copy pure calculation logic from `managers/bar_manager.py`
   - Remove all async/await (domain is sync)
   - Remove Cache/Database imports
   - Keep only bar aggregation math

6. **Create Quote domain**
   ```python
   # src/domain/quote/value_objects.py
   from dataclasses import dataclass

   @dataclass(frozen=True)
   class QuoteTick:
       price: float
       volume: float
       timestamp: int

       def __post_init__(self):
           if self.price < 0:
               raise ValueError("Price must be non-negative")
   ```

7. **Verify domain purity**
   ```bash
   # Should return NO results for I/O imports
   grep -rn "import.*motor\|import.*pymongo\|import.*redis\|import.*aiohttp" src/domain/
   ```

## Todo List

- [x] Create `src/domain/` directory structure
- [x] Create `shared/value_objects.py` (Symbol, Interval)
- [x] Create `shared/events.py` (DomainEvent base)
- [x] Create `ohlcv/aggregate.py`
- [x] Create `ohlcv/entities.py` (Bar)
- [x] Create `ohlcv/value_objects.py`
- [x] Create `ohlcv/events.py` (HistoricalDataSynced, BarCompleted)
- [x] Create `ohlcv/services/bar_builder.py`
- [x] Create `symbol/` domain
- [x] Create `quote/` domain
- [x] Verify zero I/O imports in domain
- [x] Run tests (imports verified)

## Success Criteria

- [x] Domain layer created with aggregates, entities, VOs, events
- [x] `grep` shows zero I/O imports in `src/domain/`
- [x] Value objects are frozen and hashable
- [x] Aggregates collect uncommitted events
- [x] All tests pass (imports verified)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| I/O import sneaking in | Medium | High | grep check in CI |
| Over-engineering | Medium | Low | Start minimal, expand as needed |
| Duplicate logic | Low | Low | Import from domain in services |

## Security Considerations

- Domain contains no credentials
- Pure data structures only
- No network access possible

## Next Steps

After completion:
- Phase 4 creates Mediator to dispatch to handlers
- Phase 5 refactors features to use domain objects
