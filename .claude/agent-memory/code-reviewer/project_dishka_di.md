---
name: dishka_di_migration
description: Dishka DI container pattern -- provider structure, DishkaRoute gotcha, handler registration
type: project
---

DI now uses dishka (>=1.9.1) with 6 providers in `src/providers/`.

**Why:** Replaced manual Services frozen dataclass + handler_registration.py for proper lifecycle management and auto-resolution.

**How to apply:**
- `src/container.py` = composition root (create_container + register_handlers)
- `src/providers/core_provider.py` = Settings, EventBus, Mediator
- `src/providers/persistence_provider.py` = Database, Cache, 7 repos (async generators for lifecycle)
- `src/providers/trading_provider.py` = OrderManager, PositionTracker, StrategyEngine (async generators)
- `src/providers/handler_provider.py` = 27 CQRS handlers + ALL_HANDLER_TYPES list
- Generator factories (yield) = connect/disconnect lifecycle, cleanup via container.close()
- `container.get()` is correct for APP-scoped singletons on root container
- DishkaRoute does NOT propagate to child routers via include_router() -- each leaf router needs it
