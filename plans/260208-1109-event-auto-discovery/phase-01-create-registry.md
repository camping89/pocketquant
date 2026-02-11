---
phase: 1
title: "Create Event Registry"
status: pending
effort: 45m
---

# Phase 1: Create Event Registry

## Context Links

- [EventBus](../../src/common/messaging/event_bus.py)
- [EventHandler type](../../src/common/messaging/event_handler.py)
- [DomainEvent base](../../src/domain/shared/domain_event.py)

## Overview

Create `event_registry.py` with `@event_handler` decorator and `EventRegistry` class.

## Key Insights

- EventBus already handles sync/async via `inspect.iscoroutine()`
- Instance methods need late binding (class not instantiated at decoration time)
- Keep decorator simple - just store metadata, no magic

## Requirements

### Functional
- Decorator marks methods as handlers for specific event types
- Registry collects all decorated handlers
- Support multiple handlers per event type
- Support one method handling multiple event types

### Non-Functional
- Zero runtime overhead when not collecting
- Type-safe with generics

## Architecture

```python
# Storage: list of (event_type, class, method_name)
_handler_registry: list[tuple[type[DomainEvent], type, str]] = []

def event_handler(*event_types: type[DomainEvent]):
    """Decorator to mark method as event handler."""
    def decorator(method):
        for event_type in event_types:
            _handler_registry.append((event_type, None, method.__name__))
        return method
    return decorator
```

**Instance binding strategy:**
```python
class EventRegistry:
    def register_instance(self, instance: object, event_bus: EventBus) -> None:
        """Bind instance methods and subscribe to EventBus."""
        cls = type(instance)
        for event_type, handler_cls, method_name in _handler_registry:
            if handler_cls is cls or hasattr(instance, method_name):
                method = getattr(instance, method_name)
                event_bus.subscribe(event_type, method)
```

## Related Code Files

### Create
- `src/common/messaging/event_registry.py`

### Modify
- `src/common/messaging/__init__.py` - add exports

## Implementation Steps

1. Create `event_registry.py`:

```python
"""Event handler decorator and auto-registration."""

from collections.abc import Callable
from typing import TypeVar

from src.domain.shared.domain_event import DomainEvent

T = TypeVar("T", bound=DomainEvent)

# Module-level registry: (event_type, method_name)
_handler_metadata: list[tuple[type[DomainEvent], str]] = []


def event_handler(*event_types: type[DomainEvent]) -> Callable[[T], T]:
    """Decorator to mark a method as an event handler.

    Usage:
        @event_handler(OrderFilledEvent)
        async def _on_order_filled(self, event: OrderFilledEvent) -> None:
            ...

        @event_handler(BarCompletedEvent, QuoteReceivedEvent)
        async def _on_market_event(self, event: DomainEvent) -> None:
            ...
    """
    def decorator(method: T) -> T:
        method_name = method.__name__
        for event_type in event_types:
            _handler_metadata.append((event_type, method_name))
        # Mark method with its event types for inspection
        if not hasattr(method, "_event_types"):
            method._event_types = []  # type: ignore[attr-defined]
        method._event_types.extend(event_types)  # type: ignore[attr-defined]
        return method
    return decorator


class EventRegistry:
    """Registry for auto-discovering and binding event handlers."""

    def __init__(self) -> None:
        self._registered: list[tuple[type[DomainEvent], object, str]] = []

    def register_instance(
        self,
        instance: object,
        event_bus: "EventBus"
    ) -> int:
        """Register all decorated handlers from an instance.

        Args:
            instance: Object with @event_handler decorated methods
            event_bus: EventBus to subscribe handlers to

        Returns:
            Number of handlers registered
        """
        from src.common.messaging.event_bus import EventBus

        count = 0
        # Scan instance for methods with _event_types attribute
        for attr_name in dir(instance):
            if attr_name.startswith("_") and not attr_name.startswith("__"):
                try:
                    method = getattr(instance, attr_name)
                    if callable(method) and hasattr(method, "_event_types"):
                        for event_type in method._event_types:
                            event_bus.subscribe(event_type, method)
                            self._registered.append((event_type, instance, attr_name))
                            count += 1
                except AttributeError:
                    continue
        return count

    def get_registered(self) -> list[tuple[type[DomainEvent], object, str]]:
        """Get list of registered handlers for debugging."""
        return self._registered.copy()

    def clear(self) -> None:
        """Clear registration tracking (for testing)."""
        self._registered.clear()


# Singleton registry
_registry = EventRegistry()


def get_event_registry() -> EventRegistry:
    """Get the global event registry."""
    return _registry
```

2. Update `__init__.py`:

```python
"""Event messaging for domain events."""

from src.common.messaging.event_bus import EventBus
from src.common.messaging.event_handler import EventHandler
from src.common.messaging.event_registry import (
    EventRegistry,
    event_handler,
    get_event_registry,
)

__all__ = [
    "EventBus",
    "EventHandler",
    "EventRegistry",
    "event_handler",
    "get_event_registry",
]
```

## Todo List

- [ ] Create `event_registry.py` with decorator and registry class
- [ ] Update `__init__.py` exports
- [ ] Add unit tests for decorator behavior
- [ ] Add unit tests for instance registration

## Success Criteria

- Decorator can be applied to instance methods
- EventRegistry.register_instance() subscribes to EventBus
- Multiple event types per handler works
- Type hints pass pyright

## Test Cases

```python
# tests/unit/common/test_event_registry.py

class TestEvent(DomainEvent):
    value: int

class TestHandler:
    def __init__(self):
        self.received = []

    @event_handler(TestEvent)
    async def _on_test(self, event: TestEvent) -> None:
        self.received.append(event)

async def test_register_instance_subscribes_handler():
    bus = EventBus()
    registry = EventRegistry()
    handler = TestHandler()

    count = registry.register_instance(handler, bus)

    assert count == 1
    assert bus.get_subscriber_count(TestEvent) == 1

async def test_handler_receives_events():
    bus = EventBus()
    registry = EventRegistry()
    handler = TestHandler()
    registry.register_instance(handler, bus)

    await bus.publish(TestEvent(value=42))

    assert len(handler.received) == 1
    assert handler.received[0].value == 42
```

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Decorator applied to non-method | Document as instance method only |
| Handler method renamed | Tests catch at development time |
| Circular imports | Lazy import EventBus in registry |

## Next Steps

After this phase, proceed to [Phase 2: Update Event Bus](phase-02-update-event-bus.md).
