---
phase: 3
title: "Migrate Existing Handlers"
status: pending
effort: 45m
---

# Phase 3: Migrate Existing Handlers

## Context Links

- [StrategyEngine](../../src/features/strategy/engine/strategy_engine.py) - lines 64-65
- [PositionTracker](../../src/features/trading/managers/position_tracker.py) - line 29
- [Phase 1: Registry](phase-01-create-registry.md)

## Overview

Replace manual `subscribe()` calls with `@event_handler` decorator in existing classes.

## Current Code (Before)

### StrategyEngine (strategy_engine.py:59-66)

```python
async def start(self) -> None:
    """Start the strategy engine and subscribe to events."""
    if self._running:
        return

    self._event_bus.subscribe(BarCompletedEvent, self._on_bar_completed)
    self._event_bus.subscribe(QuoteReceivedEvent, self._on_quote_received)
    self._running = True
```

### PositionTracker (position_tracker.py:26-30)

```python
async def start(self) -> None:
    """Subscribe to order events and load open positions."""
    await self.load_open_positions()
    self._event_bus.subscribe(OrderFilledEvent, self._on_order_filled)
    logger.info("position_tracker_started")
```

## Target Code (After)

### StrategyEngine

```python
from src.common.messaging import event_handler

class StrategyEngine:
    # ... __init__ unchanged ...

    async def start(self) -> None:
        """Start the strategy engine."""
        if self._running:
            return

        self._event_bus.register_handlers(self)
        self._running = True
        logger.info("strategy_engine_started")

    @event_handler(BarCompletedEvent)
    async def _on_bar_completed(self, event: BarCompletedEvent) -> None:
        """Handle bar completed event."""
        # ... existing implementation unchanged ...

    @event_handler(QuoteReceivedEvent)
    async def _on_quote_received(self, event: QuoteReceivedEvent) -> None:
        """Handle quote received event."""
        # ... existing implementation unchanged ...
```

### PositionTracker

```python
from src.common.messaging import event_handler

class PositionTracker:
    # ... __init__ unchanged ...

    async def start(self) -> None:
        """Subscribe to order events and load open positions."""
        await self.load_open_positions()
        self._event_bus.register_handlers(self)
        logger.info("position_tracker_started")

    @event_handler(OrderFilledEvent)
    async def _on_order_filled(self, event: OrderFilledEvent) -> None:
        """Handle order fill by updating position."""
        # ... existing implementation unchanged ...
```

## Related Code Files

### Modify
- `src/features/strategy/engine/strategy_engine.py`
- `src/features/trading/managers/position_tracker.py`

## Implementation Steps

### Step 1: Update StrategyEngine

1. Add import at top:
```python
from src.common.messaging import EventBus, event_handler
```

2. Add decorator to `_on_bar_completed` (around line 188):
```python
@event_handler(BarCompletedEvent)
async def _on_bar_completed(self, event: BarCompletedEvent) -> None:
```

3. Add decorator to `_on_quote_received` (around line 220):
```python
@event_handler(QuoteReceivedEvent)
async def _on_quote_received(self, event: QuoteReceivedEvent) -> None:
```

4. Update `start()` method:
```python
async def start(self) -> None:
    """Start the strategy engine and subscribe to events."""
    if self._running:
        return

    self._event_bus.register_handlers(self)
    self._running = True

    logger.info("strategy_engine_started")
```

### Step 2: Update PositionTracker

1. Add import at top:
```python
from src.common.messaging import EventBus, event_handler
```

2. Add decorator to `_on_order_filled` (around line 44):
```python
@event_handler(OrderFilledEvent)
async def _on_order_filled(self, event: OrderFilledEvent) -> None:
```

3. Update `start()` method:
```python
async def start(self) -> None:
    """Subscribe to order events and load open positions."""
    await self.load_open_positions()
    self._event_bus.register_handlers(self)
    logger.info("position_tracker_started")
```

## Todo List

- [ ] Update StrategyEngine imports
- [ ] Add @event_handler to StrategyEngine._on_bar_completed
- [ ] Add @event_handler to StrategyEngine._on_quote_received
- [ ] Update StrategyEngine.start() to use register_handlers
- [ ] Update PositionTracker imports
- [ ] Add @event_handler to PositionTracker._on_order_filled
- [ ] Update PositionTracker.start() to use register_handlers
- [ ] Run existing tests to verify no regressions

## Success Criteria

- All existing event handling works identically
- No manual subscribe() calls in migrated classes
- Tests pass without modification

## Test Verification

Run existing tests:
```bash
pytest tests/unit/features/strategy/ -v
pytest tests/unit/features/trading/ -v
```

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Handler not discovered | Test coverage, logging |
| Double registration | start() idempotency check |
| Import order issues | Standard import structure |

## Next Steps

After this phase, proceed to [Phase 4: Update Startup](phase-04-update-startup.md).
