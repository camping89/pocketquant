# Phase 3: Migrate Aggregates & Entities

## Overview
- **Priority:** P1
- **Status:** pending
- **Effort:** 40 minutes

Migrate all domain aggregates and entities from `uuid4()` to `generate_id()`.

## Key Insights

- 4 Pydantic aggregates use `Field(default_factory=uuid4)`
- 1 dataclass entity uses `field(default_factory=uuid4)`
- 2 aggregates use `str(uuid4())` in factory methods
- Tracing uses `str(uuid4())` for correlation IDs

## Files to Modify

### Pydantic Aggregates (UUID type)

| File | Field | Pattern |
|------|-------|---------|
| `src/domain/symbol/aggregate.py` | `id: UUID` | `Field(default_factory=uuid4)` |
| `src/domain/ohlcv/aggregate.py` | `id: UUID` | `Field(default_factory=uuid4)` |
| `src/domain/quote/aggregate.py` | `id: UUID` | `Field(default_factory=uuid4)` |

### Dataclass Entity (UUID type)

| File | Field | Pattern |
|------|-------|---------|
| `src/domain/ohlcv/entities.py` | `id: UUID` | `field(default_factory=uuid4)` |

### Factory Methods (str type)

| File | Usage | Pattern |
|------|-------|---------|
| `src/domain/order/aggregate.py` | `id=str(uuid4())` | In `create()` factory |
| `src/domain/position/aggregate.py` | `id=str(uuid4())` | In `open()` factory |

### Infrastructure (str type)

| File | Usage | Pattern |
|------|-------|---------|
| `src/common/tracing/context.py` | `str(uuid4())` | Fallback correlation ID |
| `src/common/tracing/correlation.py` | `str(uuid4())` | Request ID generation |
| `src/features/backtesting/engine/backtest_runner.py` | `str(uuid4())` | run_id |
| `src/features/backtesting/optimizer/grid_optimizer.py` | `str(uuid4())` | optimization_id |
| `src/infrastructure/brokers/paper/paper_broker.py` | `str(uuid4())` | broker_order_id |

## Implementation Details

### Pydantic Aggregates Pattern

```python
# Before
from uuid import UUID, uuid4
id: UUID = Field(default_factory=uuid4)

# After
from src.common.uuid import UUID, generate_id
id: UUID = Field(default_factory=generate_id)
```

### Dataclass Entity Pattern

```python
# Before
from uuid import UUID, uuid4
from dataclasses import dataclass, field
id: UUID = field(default_factory=uuid4)

# After
from dataclasses import dataclass, field
from src.common.uuid import UUID, generate_id
id: UUID = field(default_factory=generate_id)
```

### Factory Method Pattern (str IDs)

```python
# Before
from uuid import uuid4
id=str(uuid4())

# After
from src.common.uuid import generate_id_str
id=generate_id_str()
```

### Tracing Pattern

```python
# Before
from uuid import uuid4
return correlation_id if correlation_id else str(uuid4())

# After
from src.common.uuid import generate_id_str
return correlation_id if correlation_id else generate_id_str()
```

## Implementation Steps

1. **Symbol Aggregate** - Update import and Field
2. **OHLCV Aggregate** - Update import and Field
3. **Quote Aggregate** - Update import and Field
4. **Bar Entity** - Update import and field (dataclass)
5. **Order Aggregate** - Update factory method
6. **Position Aggregate** - Update factory method
7. **Tracing Context** - Update fallback generation
8. **Correlation Middleware** - Update request ID generation
9. **Backtest Runner** - Update run_id generation
10. **Grid Optimizer** - Update optimization_id generation
11. **Paper Broker** - Update broker_order_id generation

## Todo List

### Domain Aggregates
- [ ] Update `src/domain/symbol/aggregate.py`
- [ ] Update `src/domain/ohlcv/aggregate.py`
- [ ] Update `src/domain/quote/aggregate.py`
- [ ] Update `src/domain/ohlcv/entities.py`
- [ ] Update `src/domain/order/aggregate.py`
- [ ] Update `src/domain/position/aggregate.py`

### Infrastructure
- [ ] Update `src/common/tracing/context.py`
- [ ] Update `src/common/tracing/correlation.py`

### Features
- [ ] Update `src/features/backtesting/engine/backtest_runner.py`
- [ ] Update `src/features/backtesting/optimizer/grid_optimizer.py`
- [ ] Update `src/infrastructure/brokers/paper/paper_broker.py`

## Success Criteria

- All files updated to use `generate_id()` or `generate_id_str()`
- No remaining `uuid4` imports in source files
- Type checking passes: `pyright src/`
- Linting passes: `ruff check .`

## Next Steps

Proceed to Phase 4: Update tests
