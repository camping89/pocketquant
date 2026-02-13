# Phase 4: Trading Restructure + Mediator Conversion

## Priority: Medium | Effort: Medium | Risk: Medium

Folder restructure + convert from `request.app.state` to mediator pattern. 4 operations to create from inline routes.

## Context

- [Plan](plan.md) | Depends on: Phase 3
- Currently has NO operation folders — all endpoints inline in `api/routes.py`
- Bypasses mediator — uses `request.app.state.order_manager` / `.position_tracker` directly

## Current → Target

```
trading/                           trading/
├── api/                           ├── router.py
│   ├── __init__.py                ├── base/
│   └── routes.py (107 LOC inline) │   ├── __init__.py
├── managers/                      │   ├── managers/
│   ├── order_manager.py           │   │   ├── order_manager.py
│   └── position_tracker.py        │   │   └── position_tracker.py
├── models/                        │   ├── models/
│   ├── order.py                   │   │   ├── order.py
│   └── position.py                │   │   └── position.py
├── repositories/                  │   └── repositories/
│   ├── order_repository.py        │       ├── order_repository.py
│   └── position_repository.py     │       └── position_repository.py
└── __init__.py                    ├── list_orders/
                                   │   ├── __init__.py
                                   │   ├── query.py
                                   │   ├── handler.py
                                   │   └── route.py
                                   ├── get_order/
                                   │   ├── __init__.py
                                   │   ├── query.py
                                   │   ├── handler.py
                                   │   └── route.py
                                   ├── list_positions/
                                   │   ├── __init__.py
                                   │   ├── query.py
                                   │   ├── handler.py
                                   │   └── route.py
                                   └── get_position/
                                       ├── __init__.py
                                       ├── query.py
                                       ├── handler.py
                                       └── route.py
```

## Mediator Conversion

Current pattern (bypasses mediator):
```python
@router.get("/orders")
async def list_orders(request: Request) -> list[dict]:
    order_manager = request.app.state.order_manager
    return [...]
```

Target pattern (uses mediator):
```python
# list_orders/query.py
class ListOrdersQuery(BaseModel): ...

# list_orders/handler.py
class ListOrdersHandler(Handler[ListOrdersQuery, list[dict]]):
    def __init__(self, order_manager: OrderManager):
        self.order_manager = order_manager
    async def handle(self, query: ListOrdersQuery) -> list[dict]: ...

# list_orders/route.py
@router.get("/orders")
async def list_orders(mediator: Annotated[Mediator, Depends(get_mediator)]) -> list[dict]:
    return await mediator.send(ListOrdersQuery())
```

## Operations to Create

| Operation | Type | Source Endpoint | Dependencies |
|-----------|------|-----------------|--------------|
| `list_orders/` | Query | `GET /orders` | OrderManager |
| `get_order/` | Query | `GET /orders/{order_id}` | OrderManager |
| `list_positions/` | Query | `GET /positions` | PositionTracker |
| `get_position/` | Query | `GET /positions/{strategy_id}` | PositionTracker |

Each needs: `__init__.py`, `query.py`, `handler.py`, `route.py`

## Files to Modify

**Move (git mv):**
- `managers/` → `base/managers/`
- `models/` → `base/models/`
- `repositories/` → `base/repositories/`

**Create:**
- `base/__init__.py` — re-export OrderManager, PositionTracker
- `list_orders/` — query, handler, route, __init__
- `get_order/` — query, handler, route, __init__
- `list_positions/` — query, handler, route, __init__
- `get_position/` — query, handler, route, __init__
- `router.py` — aggregates 4 operation routes

**Delete:**
- `api/` folder

**Update:**
- `__init__.py` — update import paths, add query/handler exports
- `base/managers/order_manager.py` — import from repositories new path
- `base/repositories/order_repository.py` — import from models new path
- `base/repositories/position_repository.py` — import from models new path
- `main.py` (Phase 6) — register 4 new handlers with mediator

## Import Changes

| Old Path | New Path |
|----------|----------|
| `src.features.trading.api.routes` | `src.features.trading.router` |
| `src.features.trading.managers.*` | `src.features.trading.base.managers.*` |
| `src.features.trading.models.*` | `src.features.trading.base.models.*` |
| `src.features.trading.repositories.*` | `src.features.trading.base.repositories.*` |

## main.py Changes (Phase 6)

```python
# Current
from src.features.trading import OrderManager, PositionTracker
from src.features.trading.api import trading_router
app.state.order_manager = order_manager
app.state.position_tracker = position_tracker

# Target — add mediator registrations
from src.features.trading import (
    OrderManager, PositionTracker,
    ListOrdersQuery, ListOrdersHandler,
    GetOrderQuery, GetOrderHandler,
    ListPositionsQuery, ListPositionsHandler,
    GetPositionQuery, GetPositionHandler,
    trading_router,
)
mediator.register(ListOrdersQuery, ListOrdersHandler(order_manager))
mediator.register(GetOrderQuery, GetOrderHandler(order_manager))
mediator.register(ListPositionsQuery, ListPositionsHandler(position_tracker))
mediator.register(GetPositionQuery, GetPositionHandler(position_tracker))
# Keep app.state assignments for now (other features may still use them)
```

## Implementation Steps

1. Create `base/` with sub-folders: `managers/`, `models/`, `repositories/`
2. `git mv` each folder's contents into `base/`
3. Create `base/__init__.py` with re-exports
4. Create 4 operation folders with query.py, handler.py, route.py, __init__.py
5. Extract endpoint logic from `api/routes.py` into handlers (mediator pattern)
6. Create `router.py` aggregating 4 operation routes
7. Update internal imports
8. Update `trading/__init__.py` — export new queries/handlers
9. Delete `api/` folder
10. Run `ruff check` + `pyright`

## Todo

- [x] Create base/ sub-folder structure
- [x] Move infra folders to base/
- [x] Create 4 operation folders (list_orders, get_order, list_positions, get_position)
- [x] Implement query + handler for each (mediator pattern)
- [x] Create router.py
- [x] Update all internal imports
- [x] Update __init__.py exports
- [x] Delete api/ folder
- [x] Verify ruff + pyright pass

## Success Criteria

- Trading uses mediator pattern like all other features
- No `request.app.state` access in route handlers
- All 4 operations have proper query/handler/route structure
- `ruff check` + `pyright` pass
