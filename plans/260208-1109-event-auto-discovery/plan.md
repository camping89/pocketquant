---
title: "Event Handler Auto-Discovery"
description: "Replace manual subscribe() calls with decorator-based auto-discovery"
status: complete
priority: P2
effort: 3h
branch: feat/strategy-init
tags: [event-bus, decorator, auto-discovery, refactor]
created: 2026-02-08
---

# Event Handler Auto-Discovery

## Problem

Manual `subscribe()` calls scattered across codebase:
- `strategy_engine.py:64-65` - BarCompletedEvent, QuoteReceivedEvent
- `position_tracker.py:29` - OrderFilledEvent
- Future handlers require modifying `main.py` lifespan

## Solution

Decorator-based `@event_handler(EventType)` with auto-collection at startup.

```python
# Before (scattered)
self._event_bus.subscribe(BarCompletedEvent, self._on_bar_completed)

# After (declarative)
@event_handler(BarCompletedEvent)
async def _on_bar_completed(self, event: BarCompletedEvent) -> None: ...
```

## Phases

| Phase | File | Status | Est |
|-------|------|--------|-----|
| 1 | [phase-01-create-registry.md](phase-01-create-registry.md) | pending | 45m |
| 2 | [phase-02-update-event-bus.md](phase-02-update-event-bus.md) | pending | 30m |
| 3 | [phase-03-migrate-handlers.md](phase-03-migrate-handlers.md) | pending | 45m |
| 4 | [phase-04-update-startup.md](phase-04-update-startup.md) | pending | 60m |

## Architecture

```
src/common/messaging/
├── __init__.py           # Add event_handler, EventRegistry exports
├── event_bus.py          # Existing (unchanged)
├── event_handler.py      # Existing type alias
└── event_registry.py     # NEW: @event_handler decorator + registry
```

## Key Design Decisions

1. **Instance method binding**: Handlers store (class, method_name) → bound at registration
2. **Sync/async**: Already supported by EventBus.publish()
3. **Startup discovery**: Single `registry.discover_and_register()` call in lifespan
4. **No module scanning**: Explicit registration via decorator (KISS)

## Files Modified

- `src/common/messaging/event_registry.py` (NEW)
- `src/common/messaging/__init__.py`
- `src/features/strategy/engine/strategy_engine.py`
- `src/features/trading/managers/position_tracker.py`
- `src/main.py`

## Success Criteria

- [ ] All existing handlers work without manual subscribe()
- [ ] Tests pass
- [ ] New handlers only require @event_handler decorator
