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
        """Publish event to all subscribers (FIFO order).

        A raising handler does not stop the others; the first error is re-raised
        after every handler ran. The list is copied because a handler may
        subscribe or unsubscribe while it awaits.
        """
        errors: list[Exception] = []
        for handler in list(self._handlers.get(type(event), [])):
            try:
                result = handler(event)
                if inspect.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001 - re-raised below
                errors.append(exc)
        self._history.append(event)
        if errors:
            raise errors[0]

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
