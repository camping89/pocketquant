# Phase 3: Per-Feature `register_handlers()` Functions

**Priority:** High | **Status:** Pending

## Overview

Each feature provides a `register_handlers(mediator, **deps)` function that instantiates and registers its handlers. This replaces the 90-line manual registration block in main.py.

## Files to Create

| File | Feature | Handlers |
|------|---------|----------|
| `src/features/market_data/register.py` | market_data | 13 handlers |
| `src/features/backtesting/register.py` | backtesting | 5 handlers |
| `src/features/strategy/register.py` | strategy | 5 handlers |
| `src/features/trading/register.py` | trading | 4 handlers |

## Dependency Map

Each feature's `register_handlers()` receives only the deps its handlers need:

### market_data
```python
def register_handlers(
    mediator: Mediator,
    settings: Settings,
    tv_provider: TradingViewProvider,
    event_bus: EventBus,
) -> None:
```
- `SyncSymbolHandler(tv_provider, event_bus)` → needs provider + event_bus
- `BulkSyncHandler(sync_handler)` → created from SyncSymbolHandler instance
- `StartQuoteFeedHandler(settings)`, `StopQuoteFeedHandler(settings)`, etc. → settings
- `GetOHLCVHandler()`, `ListSymbolsHandler()`, status handlers → no deps or settings

### backtesting
```python
def register_handlers(
    mediator: Mediator,
    event_bus: EventBus,
    strategy_engine: StrategyEngine,
) -> None:
```
- `RunBacktestHandler(event_bus, strategy_engine)`, `RunOptimizationHandler(event_bus, strategy_engine)`
- `GetBacktestHandler()`, `GetOptimizationHandler()`, `ListBacktestsHandler()` → no deps

### strategy
```python
def register_handlers(
    mediator: Mediator,
    strategy_engine: StrategyEngine,
) -> None:
```
- All 5 handlers take `strategy_engine`

### trading
```python
def register_handlers(
    mediator: Mediator,
    order_manager: OrderManager,
    position_tracker: PositionTracker,
) -> None:
```
- Order handlers take `order_manager`, position handlers take `position_tracker`

## Implementation Pattern

Each `register.py` uses `HandlerRegistry` to auto-register:

```python
from src.common.mediator import Mediator, HandlerRegistry

def register_handlers(mediator: Mediator, ...) -> None:
    registry = HandlerRegistry()

    # Instantiate handlers with their deps
    handlers = [
        SyncSymbolHandler(tv_provider, event_bus),
        BulkSyncHandler(...),
        GetOHLCVHandler(),
        ...
    ]

    # Auto-register: reads @handles metadata from each instance
    registry.register_all(mediator, handlers)
```

`HandlerRegistry.register_all()` reads `_handles_request_type` from each handler's class decorator and calls `mediator.register()` — which throws `DuplicateHandlerError` if violated.

## Success Criteria

- [ ] Each feature has a `register.py` with `register_handlers()` function
- [ ] All 27 handlers registered through feature functions
- [ ] `DuplicateHandlerError` thrown if any feature accidentally registers duplicate
- [ ] Feature `__init__.py` exports `register_handlers`
