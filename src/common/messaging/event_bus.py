"""In-memory event bus for domain events."""

import inspect
from collections import deque
from collections.abc import Callable
from typing import Any

from src.domain.shared.events import DomainEvent


class EventBus:
    """In-memory async event bus with FIFO delivery and bounded history."""

    def __init__(self, max_history: int = 50) -> None:
        self._handlers: dict[type, list[Callable]] = {}
        self._history: deque[DomainEvent] = deque(maxlen=max_history)

    def subscribe(
        self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], Any]
    ) -> None:
        """Register handler for event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(
        self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], Any]
    ) -> bool:
        """Unregister handler for event type. Returns True if handler was found."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            return True
        return False

    async def publish(self, event: DomainEvent) -> None:
        """Publish event to all subscribers (FIFO order)."""
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            result = handler(event)
            if inspect.iscoroutine(result):
                await result
        self._history.append(event)

    async def publish_all(self, events: list[DomainEvent]) -> None:
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
