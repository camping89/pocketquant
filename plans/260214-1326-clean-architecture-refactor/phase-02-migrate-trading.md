# Phase 2: Migrate Trading (Proof-of-Concept)

## Context
- [Brainstorm](../reports/brainstorm-260214-1326-clean-architecture-refactor.md)
- [Phase 1](./phase-01-scaffold-layers.md) must complete first

## Overview
- **Priority:** P1
- **Status:** Completed
- **Effort:** 3h
- **Description:** Migrate `features/trading/base/` to proper layers. Smallest feature (4 ops) — validates the migration pattern before tackling larger features.

## Key Insights
- `order_manager.py` — I/O heavy (EventBus, broker, repository). Entire file → application layer
- `position_tracker.py` — I/O heavy (EventBus, repository). Entire file → application layer
- `models/order.py` — MongoDB document schema + aggregate mapper → infrastructure/persistence/schemas/
- `models/position.py` — MongoDB document schema + aggregate mapper → infrastructure/persistence/schemas/
- `repositories/` — MongoDB persistence → infrastructure/persistence/repositories/
- Domain aggregates already exist in `src/domain/order/` and `src/domain/position/`
- **No pure domain logic to extract** — managers are orchestration-only, domain logic lives in aggregates

## Architecture

```
BEFORE:                              AFTER:
features/trading/                    features/trading/
├── base/                            ├── router.py
│   ├── managers/                    ├── list_orders/   {query, handler, route}
│   │   ├── order_manager.py         ├── get_order/     {query, handler, route}
│   │   └── position_tracker.py      ├── list_positions/ {query, handler, route}
│   ├── models/                      └── get_position/  {query, handler, route}
│   │   ├── order.py
│   │   └── position.py              application/trading/
│   └── repositories/                ├── order_manager.py
│       ├── order_repository.py      └── position_tracker.py
│       └── position_repository.py
├── router.py                        infrastructure/persistence/
├── list_orders/                     ├── repositories/
├── get_order/                       │   ├── order_repository.py
├── list_positions/                  │   └── position_repository.py
└── get_position/                    └── schemas/
                                         ├── order_schema.py
                                         └── position_schema.py
```

## Related Code Files

### Move (source → target)
- `src/features/trading/base/managers/order_manager.py` → `src/application/trading/order_manager.py`
- `src/features/trading/base/managers/position_tracker.py` → `src/application/trading/position_tracker.py`
- `src/features/trading/base/repositories/order_repository.py` → `src/infrastructure/persistence/repositories/order_repository.py`
- `src/features/trading/base/repositories/position_repository.py` → `src/infrastructure/persistence/repositories/position_repository.py`
- `src/features/trading/base/models/order.py` → `src/infrastructure/persistence/schemas/order_schema.py`
- `src/features/trading/base/models/position.py` → `src/infrastructure/persistence/schemas/position_schema.py`

### Modify (update imports)
- `src/features/trading/list_orders/handler.py`
- `src/features/trading/get_order/handler.py`
- `src/features/trading/list_positions/handler.py`
- `src/features/trading/get_position/handler.py`
- `src/features/trading/router.py`
- `src/features/trading/__init__.py`
- `src/features/strategy/base/strategy_engine.py` (imports OrderManager, PositionTracker)

### Delete
- `src/features/trading/base/` (entire directory after migration)

## Implementation Steps

1. **Move repositories to infrastructure**
   - Copy `order_repository.py` → `src/infrastructure/persistence/repositories/order_repository.py`
   - Copy `position_repository.py` → `src/infrastructure/persistence/repositories/position_repository.py`
   - Update internal imports: `src.features.trading.base.models.OrderDocument` → `src.infrastructure.persistence.schemas.order_schema.OrderDocument`
   - Update `__init__.py` exports

2. **Move document schemas to infrastructure**
   - Copy `models/order.py` → `src/infrastructure/persistence/schemas/order_schema.py`
   - Copy `models/position.py` → `src/infrastructure/persistence/schemas/position_schema.py`
   - These are MongoDB document mappers, not domain models — they import from `src.domain.order` and `src.domain.position`
   - Keep same class names (`OrderDocument`, `PositionDocument`)

3. **Move managers to application layer**
   - Copy `order_manager.py` → `src/application/trading/order_manager.py`
   - Copy `position_tracker.py` → `src/application/trading/position_tracker.py`
   - Update imports inside:
     - `src.features.trading.base.repositories.OrderRepository` → `src.infrastructure.persistence.repositories.order_repository.OrderRepository`
     - `src.features.trading.base.repositories.PositionRepository` → `src.infrastructure.persistence.repositories.position_repository.PositionRepository`
   - Export from `src/application/trading/__init__.py`

4. **Update handler imports**
   - All 4 handlers: replace `from src.features.trading.base.managers` → `from src.application.trading`
   - All 4 handlers: replace `from src.features.trading.base.repositories` → `from src.infrastructure.persistence.repositories`
   - Check if handlers import models directly — redirect to domain or infrastructure schemas

5. **Update cross-feature imports**
   - `strategy_engine.py`: `from src.features.trading.base.managers.order_manager import OrderManager` → `from src.application.trading.order_manager import OrderManager`
   - `strategy_engine.py`: `from src.features.trading.base.managers.position_tracker import PositionTracker` → `from src.application.trading.position_tracker import PositionTracker`
   - Search entire codebase: `grep -r "features.trading.base" src/` to find ALL references

6. **Delete `features/trading/base/`**
   - Remove entire base/ directory
   - Update `features/trading/__init__.py` if it re-exports from base/

7. **Verify**
   - `python -c "from src.application.trading.order_manager import OrderManager"`
   - `python -c "from src.infrastructure.persistence.repositories.order_repository import OrderRepository"`
   - Run existing trading tests
   - Check for circular imports

## Todo List
- [ ] Move repositories to infrastructure/persistence/repositories/
- [ ] Move document schemas to infrastructure/persistence/schemas/
- [ ] Move managers to application/trading/
- [ ] Update all handler imports (4 handlers)
- [ ] Update cross-feature imports (strategy_engine.py)
- [ ] Search & fix ALL remaining `features.trading.base` references
- [ ] Delete features/trading/base/
- [ ] Run tests and verify no import errors

## Success Criteria
- `features/trading/` contains ONLY: router.py, 4 operation dirs (each with query/handler/route)
- No `base/` directory in trading
- All trading handlers import from `application.trading` and `infrastructure.persistence`
- Zero `features.trading.base` references in codebase
- All tests pass

## Risk Assessment
- **Import cascade** — Strategy engine depends on trading managers. Must update before deleting base/.
- **Circular import** — application/trading → infrastructure/persistence → domain is one-directional, safe.
- **Test breakage** — Trading tests likely import from base/. Must update test imports too.
