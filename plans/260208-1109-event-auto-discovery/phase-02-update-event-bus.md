---
phase: 2
title: "Update Event Bus"
status: pending
effort: 30m
---

# Phase 2: Update Event Bus

## Context Links

- [EventBus](../../src/common/messaging/event_bus.py)
- [Phase 1: Registry](phase-01-create-registry.md)

## Overview

Add convenience method to EventBus for bulk handler registration. Keep existing API intact.

## Key Insights

- EventBus.subscribe() already works fine
- Add `register_handlers()` as convenience method
- No breaking changes to existing code

## Requirements

### Functional
- Add method to register all handlers from an instance
- Delegate to EventRegistry internally
- Return count for logging

### Non-Functional
- Backward compatible
- No changes to existing subscribe/publish behavior

## Architecture

```python
class EventBus:
    # ... existing code ...

    def register_handlers(self, instance: object) -> int:
        """Register all @event_handler decorated methods from instance."""
        from src.common.messaging.event_registry import get_event_registry
        return get_event_registry().register_instance(instance, self)
```

## Related Code Files

### Modify
- `src/common/messaging/event_bus.py`

## Implementation Steps

1. Add `register_handlers()` method to EventBus:

```python
def register_handlers(self, instance: object) -> int:
    """Register all @event_handler decorated methods from an instance.

    Scans the instance for methods decorated with @event_handler
    and subscribes them to the appropriate event types.

    Args:
        instance: Object with @event_handler decorated methods

    Returns:
        Number of handlers registered

    Example:
        class PositionTracker:
            @event_handler(OrderFilledEvent)
            async def _on_order_filled(self, event): ...

        tracker = PositionTracker(event_bus)
        event_bus.register_handlers(tracker)  # Auto-subscribes
    """
    from src.common.messaging.event_registry import get_event_registry
    return get_event_registry().register_instance(instance, self)
```

2. Full updated `event_bus.py`:

```python
"""In-memory event bus for domain events."""

import inspect
from collections import deque
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from src.domain.shared.domain_event import DomainEvent

TEvent = TypeVar("TEvent", bound=DomainEvent)


class EventBus:
    """In-memory async event bus with FIFO delivery and bounded history."""

    def __init__(self, max_history: int = 50) -> None:
        self._handlers: dict[type, list[Callable[[Any], Any]]] = {}
        self._history: deque[DomainEvent] = deque(maxlen=max_history)

    def subscribe(
        self, event_type: type[TEvent], handler: Callable[[TEvent], Any]
    ) -> None:
        """Register handler for event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(
        self, event_type: type[TEvent], handler: Callable[[TEvent], Any]
    ) -> bool:
        """Unregister handler for event type. Returns True if handler was found."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            return True
        return False

    def register_handlers(self, instance: object) -> int:
        """Register all @event_handler decorated methods from an instance.

        Scans the instance for methods decorated with @event_handler
        and subscribes them to the appropriate event types.

        Args:
            instance: Object with @event_handler decorated methods

        Returns:
            Number of handlers registered
        """
        from src.common.messaging.event_registry import get_event_registry
        return get_event_registry().register_instance(instance, self)

    async def publish(self, event: DomainEvent) -> None:
        """Publish event to all subscribers (FIFO order)."""
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            result = handler(event)
            if inspect.iscoroutine(result):
                await result
        self._history.append(event)

    async def publish_all(self, events: Sequence[DomainEvent]) -> None:
        """Publish multiple events in order."""
        for event in events:
            await self.publish(event)

    def get_history(self, limit: int = 10) -> list[DomainEvent]:
        """Get recent events (for debugging/testing)."""
        return list(self._history)[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()

    def get_subscriber_count(self, event_type: type[DomainEvent]) -> int:
        """Get number of subscribers for an event type."""
        return len(self._handlers.get(event_type, []))

    def get_all_event_types(self) -> list[type]:
        """Get all event types with registered handlers."""
        return list(self._handlers.keys())
```

## Todo List

- [ ] Add `register_handlers()` method to EventBus
- [ ] Update existing tests if needed
- [ ] Add test for register_handlers convenience method

## Success Criteria

- `event_bus.register_handlers(instance)` works
- Existing subscribe/publish unchanged
- All existing tests pass

## Test Cases

```python
# Add to tests/unit/common/test_event_bus.py

async def test_register_handlers_from_instance():
    """Test convenience method for auto-registration."""
    bus = EventBus()

    class MyHandler:
        def __init__(self):
            self.count = 0

        @event_handler(TestEvent)
        async def _on_test(self, event: TestEvent) -> None:
            self.count += 1

    handler = MyHandler()
    count = bus.register_handlers(handler)

    assert count == 1
    await bus.publish(TestEvent())
    assert handler.count == 1
```

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Circular import | Lazy import in method body |
| API confusion | Clear docstring, optional method |

## Next Steps

After this phase, proceed to [Phase 3: Migrate Handlers](phase-03-migrate-handlers.md).
