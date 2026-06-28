import inspect
from collections import deque
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from pocketquant.core.domain.shared.events import DomainEvent

TEvent = TypeVar("TEvent", bound=DomainEvent)


class EventBus:
    def __init__(self, max_history: int = 50) -> None:
        self._handlers: dict[type, list[Callable[[Any], Any]]] = {}
        self._history: deque[DomainEvent] = deque(maxlen=max_history)

    def subscribe(self, event_type: type[TEvent], handler: Callable[[TEvent], Any]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[TEvent], handler: Callable[[TEvent], Any]) -> bool:
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

    async def publish_all(self, events: Sequence[DomainEvent]) -> None:
        """Publish multiple events in order."""
        for event in events:
            await self.publish(event)

    def get_history(self, limit: int = 10) -> list[DomainEvent]:
        return list(self._history)[-limit:]

    def clear_history(self) -> None:
        self._history.clear()

    def get_subscriber_count(self, event_type: type[DomainEvent]) -> int:
        return len(self._handlers.get(event_type, []))

    def get_all_event_types(self) -> list[type]:
        return list(self._handlers.keys())
